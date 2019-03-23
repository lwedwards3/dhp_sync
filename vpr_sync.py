import datetime as dt
import dateutil.parser
import dateutil.tz
import json
from pathlib import Path
import smtplib
from email.mime.text import MIMEText

from wunder_list import WunderList
from member_clicks import MemberClicks

'''CREDENTIALS = Path.cwd().parent / 'creds.json'
LOG_FILE = Path.cwd().parent / 'log.txt'
REQUESTS_FILE = Path.cwd().parent / 'request_list.json'
CRED_PROFILE = 'MemberClicks_email'
MEMBER_EMAIL_TEMPLATE = Path.cwd() / 'member_email_template.txt'
END_OF_DAY_EMAIL_TEMPLATE = Path.cwd() / 'end_of_day_email_template.txt'
END_OF_DAY_EMAIL_ADDRESS = 'Patrol@DruidHillsPatrol.org'
'''

class VPRSync:
    '''This Class handles the data sync between MemberClicks and Wunderlist.
    
    1. DONE Retrieve open requests from MemberClicks
    2. DONE Update each request with data saved in previous request_list (status, assets)
    3. Retrieve tasks from Wunderlist 
    4. Sync with Wunderlist:
        Match existing tasks to requests and look for:
            Change in status (send email if changed to completed)
            New assets not listed in the file.  (Send email if new assets found)
        Create new tasks for unmatched requests.  (Do not send email)
        Create new requests for unmatched (manually added) tasks (Email if complete)
    6. DONE Send emails to all members where request_list.send_email=True
    7. DONE Save request_list as json file
    
    To determine whether a vacation patrol request exists in WunderList, 
    Memberclicks request (address, due_date) are matched with 
    WunderList task (title, due_date)
    '''

    def __init__(self, auto_mode=False, test_mode=False):
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
        self.credentials_file = str(Path.cwd().parent / 'creds.json')
        self.credentials_email_profile = 'MemberClicks_email'
        self.log_file = str(Path.cwd().parent / 'log.txt')
        self.requests_file = str(Path.cwd().parent / 'request_list.json')
        self.email_template_member = str(Path.cwd() / 'self.email_template_member.txt')
        self.email_template_eod = str(Path.cwd() / 'self.email_template_eod.txt')
        self.email_address_eod = ['Patrol@DruidHillsPatrol.org','lwedwards3@gmail.com']
        self.email_address_member = ['lwedwards3@gmail.com']
        self.test_mode = test_mode
        if self.test_mode:
            self.credentials_email_profile = 'MemberClicks_email'
            self.log_file = str(Path.cwd().parent / 'test_log.txt')
            self.requests_file = str(Path.cwd().parent / 'test_request_list.json')
            self.email_template_member = str(Path.cwd() / 'test_email_template_member.txt')
            self.email_template_eod = str(Path.cwd() / 'test_email_template_eod.txt')
            self.email_address_eod = ['lwedwards@mindspring.com']
            self.email_address_member = ['lwedwards@mindspring.com']
        

    def _auto_mode(self):
        self.get_mc_requests()
        self.update_requests_from_file()
        self.sync_requests()
        self.sync_with_wl()
        self.send_member_emails()
        self.save_requests_to_file()
        self.sync_archive()
        self.post_logfile()


    def _get_credentials(self):
        '''Retrieves email credentials from a json file'''
        with open(self.credentials_file, 'r') as fp:
            data = json.load(fp)
        self.email_host = data[self.credentials_email_profile]['email_host']
        self.email_address = data[self.credentials_email_profile]['email_address']
        self.password = data[self.credentials_email_profile]['password']


    def get_mc_requests(self):
        '''Retrieves open VP requests from Memberclicks'''
        self.requests = self.mc.get_open_requests()
        self.num_requests = len(self.requests)


    def get_wl_tasks(self, archived=False):
        '''Retrieves tasks from Wunderlist.  By default, retrieves working tasks,
        but will retrieve archived tasks if archived=True'''
        if not archived:
            self.tasks = self.wl.get_tasks(list_id=self.wl.list_id)
        else:
            self.archived_tasks = self.wl.get_tasks(list_id=self.wl.archive_list_id)


    def utc_to_local(self, string_time):
        '''string_time is in ISO8601 UTC time
        Returns a string like 2018-07-18 07:15:02 AM
        '''
        t = dateutil.parser.parse(string_time)
        t = t.replace(tzinfo=dateutil.tz.tzutc())
        t = t.astimezone(dateutil.tz.tzlocal())
        t = t.strftime('%Y-%m-%d %r')
        return t


    def update_requests_from_file(self):
        print('_update_requests_from_file')

        # Get previous request list from a json file
        with open(self.requests_file, 'r') as fp:
            self.previous_requests = json.load(fp)

        for req in self.requests:
            for pre in self.previous_requests:
                if (req['address']==pre['address']) & (req['due_date']==pre['due_date']):
                    req['completed'] = pre['completed']
                    req['assets'] = pre['assets']
                

    def sync_with_wl(self):
        print('_sync_with_wl')

        def update_request_from_wl(task):
            for req in self.requests:
                try: 
                    task['due_date']
                except KeyError:
                    task['due_date']=dt.datetime.now().strftime('%Y-%M-%D')
                if (task['title'] == req['address']) & (task['due_date'] == req['due_date']):
                    if req['completed'] != task['completed']:
                        if task['completed']:
                            req['send_email'] = True
                        req['completed'] = task['completed']
                    req['task_id'] = task['id']
                    print('request updated', req['address'], req['due_date'])
                    return True
            return False

        def create_new_request(task):
            note = self.wl.get_note(task_id=task['id'])
            self.requests.append({
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

            for request in self.requests:
                
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

        self.get_wl_tasks()
        for task in self.tasks:
            if not update_request_from_wl(task):
                create_new_request(task=task)
        get_assets()
        print('Sync with WL complete')


    def sync_requests(self):
        '''Syncs vacation requests from MemberClicks to WunderList.
        For each active request in MemberClicks, this insures that a 
        task for the current day exists in Wunderlist.'''
        if not self.requests:
            self.get_mc_requests()
        if not self.tasks:
            self.get_wl_tasks()
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
        print('_save_requests_to_file')
        with open(self.requests_file, 'w') as fp:
            json.dump(self.requests, fp)


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

            if not self.tasks:
                self.get_wl_tasks()
                    
            if dt.datetime.now().hour >= 1:
                completed_tasks = []
                incomplete_tasks = []
                scheduled_tasks = []
                for task in self.tasks:
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
                    else:
                        scheduled_tasks.append(task)

            print('Archived '+str(self.num_archived_tasks)+' tasks')
            return (completed_tasks, incomplete_tasks, scheduled_tasks)

        def end_of_day_report(classified_tasks):
            '''archived_tasks is a tuple of two lists.  list0 = completed tasks
            list1 = incomplete tasks.
            Creates an end-of-day report summarizing the previous day's tasks'''
            print('eod: '+str(len(classified_tasks[0])) + ' com inc ' + str(len(classified_tasks[1])))
            if (len(classified_tasks[0]) + len(classified_tasks[1])) == 0:
                return
            
            print('end of day report')
            def list_to_string(task_list):
                '''task_list is a list of json tasks.  Returns a string with each task on separate line'''
                if len(task_list) == 0:
                    return 'None'
                response = ''
                for task in task_list:
                    response += task['title'] + '\n'
                return response

            with open(self.email_template_eod, 'r') as fp:
                body = fp.read()
            
            scheduled_tasks = []
            for tsk in classified_tasks[2]:
                if tsk['due_date'] == dt.datetime.now().strftime('%Y-%m-%d'):
                    scheduled_tasks.append(tsk)

            report_date = (dt.datetime.now() + dt.timedelta(days=-1)).strftime('%Y-%m-%d')
            completed_tasks = list_to_string(classified_tasks[0])
            incomplete_tasks = list_to_string(classified_tasks[1])
            scheduled_tasks = list_to_string(scheduled_tasks)
            
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
            assets = assets + '\t' + self.utc_to_local(asset['created_at']) + '\n'
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
                if len(req['email_address']) > 1:
                    a = 0
                    #to_addrs.append(req['email_address'])
                self.send_mail(to_addrs=to_addrs, 
                                body=body, 
                                subject='DHP Vacation Patrol Update')
                emails += 1
                print('email sent', req['address'], req['due_date'])
        print('sent '+str(emails)+' emails')


    def debug_request_summary(self):
        print('Requests summary: <address>, <due_date>, <task_id>, <completed>, <assets>, <send_email>')
        for req in self.requests:
            print(req['address'], req['due_date'], req['task_id'], 
                req['completed'], len(req['assets']), req['send_email'])
            

