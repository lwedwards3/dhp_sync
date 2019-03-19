import datetime as dt
import dateutil.parser
import dateutil.tz
import json
from pathlib import Path
import smtplib

from wunder_list import WunderList
from member_clicks import MemberClicks

CREDENTIALS = Path.cwd().parent / 'creds.json'
LOG_FILE = Path.cwd().parent / 'log.txt'
REQUESTS_FILE = Path.cwd().parent / 'request_list.json'
CRED_PROFILE = 'MemberClicks_email'
MEMBER_EMAIL_TEMPLATE = Path.cwd() / 'member_email_template.txt'
END_OF_DAY_EMAIL_TEMPLATE = Path.cwd() / 'end_of_day_email_template.txt'
END_OF_DAY_EMAIL_ADDRESS = 'Patrol@DruidHillsPatrol.org'

class VPRSync:
    '''This Class handles the data sync between MemberClicks and Wunderlist.
    
    1. DONE Retrieve open requests from MemberClicks
    2. DONE Update each request with data saved in previous request_list (status, assets)
    3. Determine if each request is new or not.
        if new: create new wl task
        if not new: add data from previous request_list.
    4. Retrieve tasks from Wunderlist and add any manually-entered vp tasks to request_list
    5. For each request in request_list:
        Get wl status.
        if status changed, then update request list and set send_email=True

        Get wl assets
        If not in request_list, then add and set send_email=True
    6. Send emails to all members where request_list.send_email=True
    7. Save request_list as json file
    
    To determine whether a vacation patrol request exists in WunderList, 
    Memberclicks request (address, due_date) are matched with 
    WunderList task (title, due_date)
    '''

    def __init__(self, auto_mode=False):
        self.mc = MemberClicks()
        self.wl = WunderList()
        self._get_credentials()
        self.mc_requests = None
        self.wl_tasks = None
        self.wl_archived_tasks = None
        self.num_requests = 0
        self.num_posted_requests = 0
        self.num_archived_tasks = 0
        if auto_mode:
            self._get_mc_requests()
            self._update_requests_from_file()
            self._sync_with_wl()
            self.send_member_emails()
            self._save_requests_to_file()
            self.sync_archive()
            self.post_logfile()


    def _get_credentials(self):
        '''Retrieves email credentials from a json file'''
        with open(str(CREDENTIALS), 'r') as fp:
            data = json.load(fp)
        self.email_host = data[CRED_PROFILE]['email_host']
        self.email_address = data[CRED_PROFILE]['email_address']
        self.password = data[CRED_PROFILE]['password']
    
    def _get_mc_requests(self):
        '''Retrieves open VP requests from Memberclicks'''
        self.mc_requests = self.mc.get_open_requests()
        self.num_requests = len(self.mc_requests)
        
    def _get_wl_tasks(self, archived=False):
        '''Retrieves tasks from Wunderlist.  By default, retrieves working tasks,
        but will retrieve archived tasks if archived=True'''
        if not archived:
            self.wl_tasks = self.wl.get_tasks(list_id=self.wl.list_id)
        else:
            self.wl_archived_tasks = self.wl.get_tasks(list_id=self.wl.archive_list_id)

    def _utc_to_local(self, string_time):
        '''string_time is in ISO8601 UTC time
        Returns a string like 2018-07-18 07:15:02 AM
        '''
        t = dateutil.parser.parse(string_time)
        t = t.replace(tzinfo=dateutil.tz.tzutc())
        t = t.astimezone(dateutil.tz.tzlocal())
        t = t.strftime('%Y-%m-%d %r')
        return t

    def _update_requests_from_file(self):
        print('_update_requests_from_file')
        def get_previous_requests():
                '''Retrieves the previous request list from a json file'''
                with open(str(REQUESTS_FILE), 'r') as fp:
                    self.previous_requests = json.load(fp)

        get_previous_requests()
        for req in self.mc_requests:
            for pre in self.previous_requests:
                if (req['address']==pre['address']) & (req['due_date']==pre['due_date']):
                    req['completed'] = pre['completed']
                    req['assets'] = pre['assets']
                
    def _sync_with_wl(self):
        print('_sync_with_wl')

        def update_request_from_wl(task):
            for req in self.mc_requests:
                try: 
                    task['due_date']
                except KeyError:
                    task['due_date']=dt.datetime.now().strftime('%Y-%M-%D')
                if (task['title'] == req['address']) & (task['due_date'] == req['due_date']):
                    if not req['completed'] == task['completed']:
                        req['send_email'] = True
                    req['task_id'] = task['id']
                    req['completed'] = task['completed']
                    print('request updated')
                    return True
            return False

        def create_new_request(task):
            note = self.wl.get_note(task_id=task['id'])
            self.mc_requests.append({
                'address' : task['title'],
                'due_date' : task['due_date'],
                'officer_notes' : '' if not note else note,
                'member_name' : '',
                'email_address' : '',
                'task_id' : task['id'],
                'completed' : task['completed'],
                'assets' : [],
                'send_email' : task['completed']
            })
            print('request added')

        def get_assets():
            def asset_exists(asset_id, assets):
                for asset in assets:
                    if asset['id'] == asset_id:
                        return True
                return False

            for request in self.mc_requests:
                
                if not request['task_id']=='':
                    print('task_id:', request['task_id'])
                    comments = self.wl.get_task_comments(task_id=request['task_id'])
                    print('comments:',comments)
                    for comment in comments:
                        if not asset_exists(comment['id'], request['assets']):
                            request['assets'].append({
                                'id' : comment['id'],
                                'created_at' : comment['created_at'],
                                'text' : comment['text'],
                                'type' : 'comment'
                            })
                            request['send_email']=True
                            print('comment added')

                print('about to get files',request['task_id'],request['address'])
                files = self.wl.get_task_files(task_id=request['task_id'])
                for file in files:
                    if not asset_exists(file['id'], request['assets']):
                        request['assets'].append({
                            'id' : file['id'],
                            'created_at' : file['created_at'],
                            'text' : file['url'],
                            'type' : 'file'
                        })
                        request['send_email']=True
                        print('file added')

        self._get_wl_tasks()
        for task in self.wl_tasks:
            if not update_request_from_wl(task):
                create_new_request(task=task)
        get_assets()
        print('Sync with WL complete')


    def _save_requests_to_file(self):
        '''Dumps the current VP Request from Memberclicks to a json file'''
        print('_save_requests_to_file')
        with open(str(REQUESTS_FILE), 'w') as fp:
            json.dump(self.mc_requests, fp)


    def sync_archive(self):
        '''Moves expired tasks to archive list.  A task is expired if 
        1. the due_date was yesterday or earlier
        2. the current time is past 1 AM
        '''
        print('sync_archive')

        def archive_tasks():
            print('archive_tasks')
            date_format = '%Y-%m-%d'
            cutoff_date = dt.datetime.now() + dt.timedelta(days=-1)
            self.num_archived_tasks = 0

            if not self.wl_tasks:
                self._get_wl_tasks()
                    
            if dt.datetime.now().hour >= 1:
                completed_tasks = []
                incomplete_tasks = []
                for task in self.wl_tasks:
                    due = dt.datetime.strptime(task['due_date'],date_format)
                    if due <= cutoff_date:
                        print('archive task', task['id'], task['revision'])

                        if task['completed']==True:
                            completed_tasks.append(task)
                        else:
                            incomplete_tasks.append(task)

                        self.wl.archive_task(task_id=task['id'],
                                        revision=task['revision'])
                        self.num_archived_tasks += 1

            print('Archived '+str(self.num_archived_tasks)+' tasks')
            return (completed_tasks, incomplete_tasks)

        def end_of_day_report(archived_tasks):
            '''archived_tasks is a tuple of two lists.  list0 = completed tasks
            list1 = incomplete tasks.
            Creates an end-of-day report summarizing the previous day's tasks'''
            print('eod: '+str(len(archived_tasks[0])) + ' com inc ' + str(len(archived_tasks[1])))
            if (len(archived_tasks[0]) + len(archived_tasks[1])) == 0:
                return
            
            print('end of day report')
            def list_to_string(task_list):
                '''lst is a list of tasks.  Returns a string with each task on separate line'''
                if len(task_list) == 0:
                    return 'None'
                response = ''
                for task in task_list:
                    response += task['title'] + '\n'
                return response

            with open(str(END_OF_DAY_EMAIL_TEMPLATE), 'r') as fp:
                body = fp.read()

            report_date = (dt.datetime.now() + dt.timedelta(days=-1)).strftime('%Y-%m-%d')
            completed_tasks = list_to_string(archived_tasks[0])
            incomplete_tasks = list_to_string(archived_tasks[1])
            
            msg = body.format(report_date,
                                completed_tasks,
                                incomplete_tasks)

            self.send_mail(to_addrs=['louis.edwards@novelis.com',END_OF_DAY_EMAIL_ADDRESS], 
                            msg=msg, 
                            subject='DHP End of Day Vacation Patrol Report')

        archived_tasks = archive_tasks()
        end_of_day_report(archived_tasks)


    def post_logfile(self):
        '''Records the summary statistics from each sync session to a log file.'''
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


    def send_mail(self, to_addrs, msg, subject=None):
        if not type(to_addrs) == list:
            to_addrs = [to_addrs]
            print(to_addrs)
        if subject:
            msg = 'Subject: {}\n\n{}'.format(subject, msg)
        with smtplib.SMTP_SSL(self.email_host, 465) as server:
            server.login(self.email_address, self.password)
            server.sendmail(from_addr=self.email_address,
                        to_addrs=to_addrs,
                        msg=msg)
    
    def send_member_emails(self):
        '''For each request flagged as send_email
        Creates an email document and sends it.'''
        with open(str(MEMBER_EMAIL_TEMPLATE), 'r') as fp:
            body = fp.read()

        emails = 0
        for req in self.mc_requests:
            if req['send_email']==True:
                assets = ''
                for asset in req['assets']:
                    assets = assets + self._utc_to_local(asset['created_at']) + '\n'
                    assets = assets + asset['text'] + '\n\n'
                if req['completed']==True:
                    status = 'We completed your patrol, but will continue to watch for suspicious activity.'
                else:
                    status = 'We have not completed your patrol for today.'

                msg = body.format(req['due_date'],
                                    req['address'],
                                    assets,
                                    status)

                self.send_mail(to_addrs='louis.edwards@novelis.com', 
                                msg=msg, 
                                subject='Vacation Patrol Update')
                emails += 1
                print('email sent')
        print('sent '+str(emails)+' emails')

