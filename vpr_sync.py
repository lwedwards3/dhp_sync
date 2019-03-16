'''
================================================================
Version: DEV
Date:    2019-03-14
Name:    Louis Edwards
Description:
    Changed assignment of VPRSync.access_token_expires
    
================================================================
Version: 0.1
Date:    2019-03-13
Name:    Louis Edwards
Description:
    Added task archive process
    Development on comments and files, but these are not ready for service.
===============================================================

This project syncs vacation requests from the DHP's MemberClicks account
with a WunderList task list that is accessible by the patrol officers
from the shared iPhone.

It contains three classes:
    
MemberClicks: Provides a method to obtain current vacation request data.

WunderList: Provides methods to:
    1. Obtain current tasks (both open and closed)
    2. Create new tasks, and add Notes to a task.
    
VPRSync: Syncronizes WunderList with MemberClicks.  At present, this goes in
one direction: New requests from MemberClicks are added to WunderList
'''

import datetime as dt
import json
from pathlib import Path
import smtplib

from wunder_list import WunderList
from member_clicks import MemberClicks

CREDENTIALS = Path.cwd().parent / 'creds.json'
LOG_FILE = Path.cwd().parent / 'log.txt'
CRED_PROFILE = 'MemberClicks_email'

class VPRSync:
    '''This Class handles the data sync between MemberClicks and Wunderlist.
    
    1. Retrieve open requests from MemberClicks
    2. Retrieve tasks from WunderList (both complete and open)
    3. Determine which MC requests do not exist in WL and add them.
    
    To determine whether a vacation patrol request exists in WunderList, 
    Memberclicks request (address, patrol_date) are matched with 
    WunderList task (title, due_date)
    '''

    def __init__(self, auto_mode=False):
        self.mc = MemberClicks()
        self.wl = WunderList()
        self.mc_requests = None
        self.wl_tasks = None
        self.wl_archived_tasks = None
        self.num_requests = 0
        self.num_posted_requests = 0
        self.num_archived_tasks = 0
        if auto_mode:
            self.sync_requests()
            #self.sync_assets()
            self.sync_archive()
            self.post_logfile()
            self.test_email()
        
    def _get_credentials(self):
        with open(str(CREDENTIALS), 'r') as fp:
            data = json.load(fp)
        self.email_host = data[CRED_PROFILE]['email_host']
        self.email_address = data[CRED_PROFILE]['email_address']
        self.password = data[CRED_PROFILE]['password']
    
    def _get_mc_requests(self):
        self.mc_requests = self.mc.get_open_requests()
        self.num_requests = len(self.mc_requests)
        
    def _get_wl_tasks(self, archived=False):
        if not archived:
            self.wl_tasks = self.wl.get_tasks(list_id=self.wl.list_id)
        else:
            self.wl_archived_tasks = self.wl.get_tasks(list_id=self.wl.archive_list_id)

    def create_request_file(self):
        with open('vacation_patrol_requests.json', 'w') as fp:
            json.dump(self.mc_requests, fp)

    def sync_requests(self):
        '''Syncs vacation requests from MemberClicks to WunderList.
        For each active request in MemberClicks, this insures that a 
        task for the current day exists in Wunderlist.'''
        if not self.mc_requests:
            self._get_mc_requests()
        if not self.wl_tasks:
            self._get_wl_tasks()
        self.num_posted_requests = 0
        
        tasks_index = [(task['title'],task['due_date']) for task in self.wl_tasks]
        
        for request in self.mc_requests:
            if not request[0] in tasks_index:
                address = request[0][0]
                due_date = request[0][1]
                print((address, due_date))
                task_id = self.wl.post_new_task(address, due_date)['id']
                note = '\n'.join(request[1])
                self.wl.post_new_note(task_id, note)
                self.num_posted_requests += 1
        print('Posted: '+str(self.num_posted_requests)+' requests')

    def _retrieve_assets(self):
        '''Checks Wunderlist for new task_comments and files.
        Emails member with each new asset.
        Records assets in archive file.'''
        assets = {}
        def check_assets(task_id):
            if not task_id in assets.keys():
                assets[task_id] = {'comments' : {}, 'files' : {}}

        # First, COMMENTS for the incomplete tasks
        comments = self.wl.get_list_comments()
        for comment in comments:
            task_id = comment['task_id']
            check_assets(task_id)
            assets[task_id]['comments'][comment['id']] = {
                  'created_at' : comment['created_at'],
                  'text' : comment['text'],
                  'sentYN' : False}
            
        # Next, FILES for the incomplete tasks
        files = self.wl.get_list_files()
        for file in files:
            task_id = file['task_id']
            check_assets(task_id)
            assets[task_id]['files'][file['id']] = {
                  'created_at' : file['created_at'],
                  'url' : file['url'],
                  'sentYN' : False}

        # Next, ASSETS for the completed tasks
        for task in self.wl_tasks:
            if task['completed']:
                # COMMENTS
                comments = self.wl.get_task_comments(task['id'])
                for comment in comments:
                    task_id = comment['task_id']
                    check_assets(task_id)
                    assets[task_id]['comments'][comment['id']] = {
                          'created_at' : comment['created_at'],
                          'text' : comment['text'],
                          'sentYN' : False}
    
                # Next, FILES for the completed tasks
                files = self.wl.get_task_files(task['id'])
                for file in files:
                    task_id = file['task_id']
                    check_assets(task_id)
                    assets[task_id]['files'][file['id']] = {
                          'created_at' : file['created_at'],
                          'url' : file['url'],
                          'sentYN' : False}
        return assets

    def find_unsent_assets(self):
        task_assets = self._retrieve_assets()
        with open('assets.json', 'r') as fp:
            file_assets = json.load(fp)
        
        def check_sent(task_id, asset_type, asset_id):
            task_id = str(task_id)
            if not task_id in file_assets.keys():
                return False
            if asset_type == 'comment':
                return str(asset_id) in file_assets[task_id]['comments'].keys()
            else:
                return str(asset_id) in file_assets[task_id]['files'].keys()
        
        messages = []
        for task_key, task_value in task_assets.items():
            message_text = ''
            for asset_key, asset_value in task_value['comments'].items():
                if not check_sent(task_key, 'comment', asset_key):
                    message_text = message_text + asset_value['created_at'] \
                    + ': ' + asset_value['text'] + '\n\n'
            for asset_key, asset_value in task_value['files'].items():
                if not check_sent(task_key, 'file', asset_key):
                    message_text = message_text + asset_value['created_at'] \
                    + ': ' + asset_value['text'] + '\n\n'
            messages.append([task_key, message_text])
        return messages            
        
    def sync_archive(self):
        '''Moves expired tasks to archive list.  A task is expired if 
        1. the due_date was yesterday or earlier
        2. the current time is past 1 AM
        '''
        date_format = '%Y-%m-%d'
        cutoff_date = dt.datetime.now() + dt.timedelta(days=-1)
        self.num_archived_tasks = 0

        if not self.wl_tasks:
            self._get_wl_tasks()
                
        if dt.datetime.now().hour >= 1:
            for task in self.wl_tasks:
                due = dt.datetime.strptime(task['due_date'],date_format)
                if due <= cutoff_date:
                    print(task['id'], task['revision'])
                    self.wl.archive_task(task_id=task['id'],
                                    revision=task['revision'])
                    self.num_archived_tasks += 1
        #self._get_wl_tasks()
        

    def post_logfile(self):
        if self.num_archived_tasks == 0:
            str_archive = ''
        else:
            str_archive = '\tArchived tasks: ' + str(self.num_archived_tasks)
        str_line = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\t' + 'Open requests: '\
        + str(self.num_requests) + '\t' + 'Posted requests: '\
        + str(self.num_posted_requests) + str_archive + '\n'
        print(str_line)
        with open(str(LOG_FILE), 'a') as f:
            f.write(str_line)


    ### FUTURE ################################################################
    def send_mail(self, to_addrs, msg, subject=None):
        if not type(to_addrs) == list:
            to_addrs = list(to_addrs)
        if subject:
            msg = 'Subject: {}\n\n{}'.format(subject, msg)
        with smtplib.SMTP_SSL(self.email_host, 465) as server:
            server.login(self.email_address, self.password)
            server.sendmail(from_addr=self.email_address,
                        to_addrs=to_addrs,
                        msg=msg)

    def test_email(self):
        self.send_email('lwedwards3@gmail.com','This is a test message.', 'From VPS')
    
    def email_member_when_complete(self):
        '''Identifies completed Wunderlist requests and emails the member.
        
        1. Get completed tasks
        2. Determine if member has been notified
        3. Get any comments.
        4. Get any files.
        5. Email member that task is complete.  
            Include comments and link to files in the email.
        
        How to determine if member has been emailed?
            '''
        return 0
    
    def email_requests_not_completed(self):
        '''Identifies Wunderlist requests that were not completed on time.  
        Emails a list of these to the DHP board'''
        return 0

vprs = VPRSync(auto_mode=True)
