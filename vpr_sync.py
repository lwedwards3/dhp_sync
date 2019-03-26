'''
======================= TO DO ==================================

Tag all request with their source (memberclicks or wunderlist)
- DONE Alter get_mc_requests (source: 'memberclicks')
- DONE Alter sync_with_wl (wl not in mc - soruce: 'wunderlist')
- Get profile for manually-entered tasks

================================================================
'''


import datetime as dt
import dateutil.parser
import dateutil.tz
import json
from pathlib import Path
import smtplib
from email.mime.text import MIMEText

from wunder_list import WunderList
from member_clicks import MemberClicks

class VPRSync:
    '''This Class handles the data sync between MemberClicks and Wunderlist.
    
    1. DONE Retrieve open requests from MemberClicks
    2. DONE Update each request with data saved in previous request_list (status, assets)
    3. DONE Retrieve tasks from Wunderlist 
    4. Sync with Wunderlist:
        a. DONE Add new requests to WL 
        b. DONE Update request.status with info from tasks (send_mail if status changed to complete.)
        c. DONE Add manually-added tasks to requests
        d. Retrieve MC profile for manually added tasks.
        e. DONE Search for new assets not listed in the file.  (Send email if new assets found)
    6. DONE Send emails to all members where request_list.send_email=True
    7. DONE Save request_list as json file
    8. DONE Archive yesterday's tasks
    9. DONE Send EOD email when tasks are archived. 

    To determine whether a vacation patrol request exists in WunderList, 
    Memberclicks request (address, due_date) are matched with 
    WunderList task (title, due_date)
    '''

    def __init__(self, auto_mode=False, test_mode=False):
        print('VPRSync() branch: fix_unnecessary email')
        self._set_variables(test_mode)
        self.mc = MemberClicks()
        self.wl = WunderList(test_mode)
        self._get_credentials()
        if auto_mode:
            self._auto_mode()
        

    def _set_variables(self, test_mode):
        self.requests = None
        self.tasks = None
        self.archived_tasks = None
        self.num_requests = 0
        self.num_posted_requests = 0
        self.num_archived_tasks = 0
        self.num_emails = 0
        self.date_format = '%Y-%m-%d'
        self.credentials_file = str(Path.cwd().parent / 'creds.json')
        self.credentials_email_profile = 'MemberClicks_email'
        self.log_file = str(Path.cwd().parent / 'log.txt')
        self.requests_file = str(Path.cwd().parent / 'request_list.json')
        self.email_template_member = str(Path.cwd() / 'email_template_member.txt')
        self.email_template_eod = str(Path.cwd() / 'email_template_eod.txt')
        self.email_address_eod = ['Patrol@DruidHillsPatrol.org','lwedwards3@gmail.com']
        self.email_address_member = ['lwedwards3@gmail.com']
        self.email_members_flag = False
        self.test_mode = test_mode
        if self.test_mode:
            self.credentials_email_profile = 'MemberClicks_email'
            self.log_file = str(Path.cwd().parent / 'test_log.txt')
            self.requests_file = str(Path.cwd().parent / 'test_request_list.json')
            self.email_template_member = str(Path.cwd() / 'test_email_template_member.txt')
            self.email_template_eod = str(Path.cwd() / 'test_email_template_eod.txt')
            self.email_address_eod = ['lwedwards@mindspring.com']
            self.email_address_member = ['lwedwards@mindspring.com']
            self.email_members_flag = False
        

    def _auto_mode(self):
        self._get_mc_requests()
        self.sync_with_wl()
        self.send_member_emails()
        self.save_requests_to_file()
        self.archive_expired_tasks()
        self.post_logfile()


    def _get_mc_requests(self):
        '''Retrieves open VP requests from Memberclicks and 
        adds these to request list.
        Then updates requests with info from json file'''
        print('_get_mc_requests')
        self.requests = self.mc.get_open_requests()
        self.num_requests = len(self.requests)

        # Get previous request list from a json file
        with open(self.requests_file, 'r') as fp:
            self.previous_requests = json.load(fp)
        for req in self.requests:
            req['source'] = 'memberclicks'
            for pre in self.previous_requests:
                if (req['address']==pre['address']) & (req['due_date']==pre['due_date']):
                    req['completed'] = pre['completed']
                    req['assets'] = pre['assets']
                    req['send_email'] = False
                    if 'source' in pre.keys():
                        req['source'] = pre['source']


    def _get_wl_tasks(self, archived=False):
        '''Retrieves tasks from Wunderlist.  By default, retrieves working tasks,
        but will retrieve archived tasks if archived=True'''
        if not archived:
            self.tasks = self.wl.get_tasks(list_id=self.wl.list_id)
        else:
            self.archived_tasks = self.wl.get_tasks(list_id=self.wl.archive_list_id)

        for task in self.tasks:
            # due_date = today if missing
            try: 
                task['due_date']
            except KeyError:
                task['due_date']=(dt.datetime.now() + dt.timedelta(hours=1)).strftime(self.date_format)
            


    def sync_with_wl(self):
        ''' 
        1. Create tasks from new requests
        2. Update requests with task info
        3. Del WL if no MC and source = memberclicks
        '''
        print('_sync_with_wl')
        if not self.requests:
            self._get_mc_requests()
        if not self.tasks:
            self._get_wl_tasks()
        
        self._create_tasks_for_new_requests()
        self._push_tasks_to_requests()
        self._get_wl_assets()
        print('Sync with WL complete')


    def _push_tasks_to_requests(self):
        '''For each TASK updates the status of related REQUEST
        If TASK not found, add to REQUESTS
        Finally, retrieve task ASSETS and add to REQUEST''' 
        for task in self.tasks:
            if not self._update_requests_with_wl_info(task=task):
                self._create_request_for_manual_task(task=task)
            #self._get_task_assets(task)


    def _update_requests_with_wl_info(self, task):
        '''task is a wunderlist task
        Finds matching request and updates with info from the task.
        Returns True if task was found in requests, otherwise False.''' 
        for req in self.requests:
            if (task['title'] == req['address']) & (task['due_date'] == req['due_date']):
                # send_mail = True if newly completed.
                if req['completed'] != task['completed']:
                    if task['completed']:
                        req['send_email'] = True
                    req['completed'] = task['completed']
                req['task_id'] = task['id']
                print('request updated', req['address'], req['due_date'])
                return True
        
        for req in self.previous_requests:
            if task['id'] == req['task_id']:
                if req['completed'] != task['completed']:
                    if task['completed']:
                        req['send_email'] = True
                    req['completed'] = task['completed']
                self.requests.append(req)
                print('request updated', req['address'], req['due_date'])
                return True
        return False

    def _create_request_for_manual_task(self, task):
            '''if a task was manually added to WL, this will add it to the requests list'''
            note = self.wl.get_note(task_id=task['id'])
            
            mc_profiles = self.mc.get_address_profiles(task['title'])
            if len(mc_profiles)==1:
                self.requests.append({
                    'address' : mc_profiles[0]['title'],
                    'due_date' : task['due_date'],
                    'member_name' : mc_profiles[0]['member_name'],
                    'email_address' : mc_profiles[0]['email_address'],
                    'task_id' : task['id'],
                    'completed' : task['completed'],
                    'assets' : [],
                    'send_email' : task['completed'],
                    'source' : 'wunderlist',
                    'officer_notes' : note + '\n' + mc_profiles[0]['officer_notes']
                })
                print('manual request added with member profile')
            else:
                self.requests.append({
                    'address' : task['title'],
                    'due_date' : task['due_date'],
                    'member_name' : '',
                    'email_address' : '',
                    'task_id' : task['id'],
                    'completed' : task['completed'],
                    'assets' : [],
                    'send_email' : task['completed'],
                    'source' : 'wunderlist',
                    'officer_notes' : '' if not note else note
                })
            print('manual request added')
    
    
    def _create_tasks_for_new_requests(self):
        '''Syncs vacation requests from MemberClicks to WunderList.
        For each active request in MemberClicks, this insures that a 
        task for the current day exists in Wunderlist.'''
        if not self.requests:
            self._get_mc_requests()
        if not self.tasks:
            self._get_wl_tasks()
        self.num_posted_requests = 0
        
        tasks_index = [(task['title'],task['due_date']) for task in self.tasks]
        
        for request in self.requests:
            if not (request['address'],request['due_date']) in tasks_index:
                address = request['address']
                due_date = request['due_date']
                print('adding task for ',(address, due_date))
                request['task_id'] = self.wl.post_new_task(address, due_date)['id']
                note = '\n'.join(request['officer_notes'])
                self.wl.post_new_note(request['task_id'], note)
                self.num_posted_requests += 1
        print('Posted: '+ str(self.num_posted_requests) +' requests')
    

    def save_requests_to_file(self):
        '''Dumps the current VP Request from Memberclicks to a json file'''
        print('save_requests_to_file')
        with open(self.requests_file, 'w') as fp:
            json.dump(self.requests, fp)

    def _find_request(self, task):
        response = None
        for request in self.requests:
            if (request['addresss']==task['title']) & (request['due_date']==task['due_date']):
                response = request['task_id']
        return response


    def _get_wl_assets(self):
        def asset_is_new(asset_id, assets):
            for asset in assets:
                if asset['id'] == asset_id:
                    return False
            return True

        for request in self.requests:               
            if not request['task_id']=='':
                print('task_id:', request['task_id'])
                comments = self.wl.get_task_comments(task_id=request['task_id'])
                # add num_comments to self.tasks
                self._add_task_attribute(request['task_id'], 'num_comments', len(comments))
                print('comments:',comments)
                for comment in comments:
                    if asset_is_new(comment['id'], request['assets']):
                        request['assets'].append({
                            'id' : comment['id'],
                            'created_at' : comment['created_at'],
                            'text' : comment['text'],
                            'type' : 'comment'
                        })
                        request['send_email']=True # Flag to email new comment
                        print('comment added')

            print('about to get files',request['task_id'],request['address'])
            files = self.wl.get_task_files(task_id=request['task_id'])
            # Add number of files to self.tasks
            self._add_task_attribute(request['task_id'], 'num_files', len(files))
            for file in files:
                if not asset_is_new(file['id'], request['assets']):
                    request['assets'].append({
                        'id' : file['id'],
                        'created_at' : file['created_at'],
                        'text' : file['url'],
                        'type' : 'file'
                    })
                    request['send_email']=True # Flag to email new file
                    print('file added')


    def archive_expired_tasks(self):
        '''Moves expired tasks to archive list.  A task is expired if 
        1. the due_date was yesterday or earlier
        2. the current time is past 1 AM
        '''
        print('archive_expired_tasks')

        def archive_tasks():
            print('archive_tasks')
            cutoff_date = dt.datetime.now() + dt.timedelta(days=-1)
            self.num_archived_tasks = 0

            if not self.tasks:
                self._get_wl_tasks()
                    
            if dt.datetime.now().hour >= 1:
                completed_tasks = []
                incomplete_tasks = []
                scheduled_tasks = []
                for task in self.tasks:
                    due = dt.datetime.strptime(task['due_date'],self.date_format)
                    if due <= cutoff_date:
                        print('archive task:', task['id'], task['revision'])

                        if task['completed']==True:
                            completed_tasks.append(task)
                        else:
                            incomplete_tasks.append(task)

                        self.wl.archive_task(task_id=task['id'],
                                        revision=task['revision'])
                        self.num_archived_tasks += 1
                    else:
                        scheduled_tasks.append(task)

            print('Archived '+str(self.num_archived_tasks)+' tasks')
            return (completed_tasks, incomplete_tasks, scheduled_tasks)

        def end_of_day_report(classified_tasks):
            '''Classified_tasks is a tuple of three lists.  list0 = completed tasks
            list1 = incomplete tasks, list2 = scheduled_tasks.
            Creates an end-of-day report summarizing the previous day's tasks'''
            print('eod: '+str(len(classified_tasks[0])) + ' completed / incomplete: ' + str(len(classified_tasks[1])))
            if (len(classified_tasks[0]) + len(classified_tasks[1])) == 0:
                return
            
            print('end of day report')
            def list_to_string(task_list):
                '''task_list is a list of json tasks.  Returns a string with each task on separate line'''
                if len(task_list) == 0:
                    return 'None'
                response = ''
                for task in task_list:
                    response += task['title'] + '\t'
                    if 'num_comments' in task.keys():
                        if task['num_comments'] >0:
                            response += 'Cmt' + str(task['num_comments']) + ' '
                    if 'num_files' in task.keys():
                        if task['num_files'] >0:
                            response += 'Pho' + str(task['num_files'])
                    response += '\n'
                return response

            with open(self.email_template_eod, 'r') as fp:
                body = fp.read()
            
            report_date = (dt.datetime.now() + dt.timedelta(days=-1)).strftime(self.date_format)
            completed_tasks = list_to_string(classified_tasks[0])
            incomplete_tasks = list_to_string(classified_tasks[1])
            scheduled_tasks = list_to_string(classified_tasks[2])
            
            msg = body.format(report_date,
                                completed_tasks,
                                incomplete_tasks,
                                scheduled_tasks)

            self.send_mail(to_addrs=self.email_address_eod, 
                            body=msg, 
                            subject='DHP End of Day Vacation Patrol Report')

        classified_tasks = archive_tasks()
        end_of_day_report(classified_tasks)


    def post_logfile(self):
        '''Records the summary statistics from each sync session to a log file.'''
        if self.num_archived_tasks == 0:
            str_archive = ''
        else:
            str_archive = '\tArchived tasks: ' + str(self.num_archived_tasks)
        str_line = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\t' + 'Open requests: '\
        + str(self.num_requests) + '\t' + 'Posted requests: '\
        + str(self.num_posted_requests) + '\tEmails sent: '\
        + str(self.num_emails) + str_archive + '\n'
        print(str_line)
        with open(self.log_file, 'a') as f:
            f.write(str_line)


    def send_mail(self, to_addrs, body, subject=None):
        if type(to_addrs) == list:
            to_addrs = ','.join(to_addrs)
        
        msg = MIMEText(body)
        msg['From'] = 'DHP Vacation Patrol<VacationPatrol@DruidHillsPatrol.org>'
        msg['To'] = to_addrs
        msg['Subject'] = subject
        
        print('Email to:',to_addrs, subject)
        with smtplib.SMTP_SSL(self.email_host, 465) as server:
            server.login(self.email_address, self.password)
            server.send_message(msg)
        self.num_emails += 1

    
    def create_message_body(self, request):
        '''request is a dictionary of data for an individual request.
        Creates message body by merging address, date and assets
        with a message template stored on disk.'''
        assets = ''
        for asset in request['assets']:
            assets = assets + '\t' + self._utc_to_local(asset['created_at']) + '\n'
            assets = assets + '\t' + asset['text'] + '\n\n'

        if len(assets) > 1:
            assets = 'Updates:\n\n' + assets

        # gets the email template
        with open(self.email_template_member, 'r') as fp:
            template = fp.read()

        return template.format(request['address'],
                            request['due_date'],
                            assets)


    def send_member_emails(self):
        '''For each request where send_email = True
        Creates an email document and sends it.'''
        emails = 0
        for req in self.requests:
            if req['send_email']==True:
                body = self.create_message_body(req)
                to_addrs = self.email_address_member.copy()
                if self.email_members_flag:
                    if 'email_address' in req.keys():
                        if len(req['email_address']) > 1:
                            to_addrs.append(req['email_address'])
                
                self.send_mail(to_addrs=to_addrs, 
                                body=body, 
                                subject='DHP Vacation Patrol Update')
                emails += 1
                req['send_email'] = False
                print('email sent', req['address'], req['due_date'])
        print('sent '+str(emails)+' emails')



    def _utc_to_local(self, string_time):
        '''string_time is in ISO8601 UTC time
        Returns a string like 2018-07-18 07:15:02 AM
        '''
        t = dateutil.parser.parse(string_time)
        t = t.replace(tzinfo=dateutil.tz.tzutc())
        t = t.astimezone(dateutil.tz.tzlocal())
        t = t.strftime('%Y-%m-%d %r')
        return t

    def _add_task_attribute(self, task_id, key, value):
        print('add attribute', task_id, key, value)
        for task in self.tasks:
            if task['id']==task_id:
                task[key]=value


    def _get_credentials(self):
        '''Retrieves email credentials from a json file'''
        with open(self.credentials_file, 'r') as fp:
            data = json.load(fp)
        self.email_host = data[self.credentials_email_profile]['email_host']
        self.email_address = data[self.credentials_email_profile]['email_address']
        self.password = data[self.credentials_email_profile]['password']


    def debug_request_summary(self):
        print('Requests summary: <address>, <due_date>, <task_id>, <completed>, <assets>, <send_email>')
        for req in self.requests:
            print(req['address'], req['due_date'], req['task_id'], 
                req['completed'], len(req['assets']), req['send_email'])
            

