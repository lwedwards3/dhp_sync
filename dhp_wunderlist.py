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

import sys
import datetime as dt
import json
from pathlib import Path
from requests_oauthlib import OAuth2Session
from requests.auth import HTTPBasicAuth
from oauthlib.oauth2 import BackendApplicationClient
import wunderpy3

CREDENTIALS = Path.cwd() / 'creds.json'
LOG_FILE = Path.cwd() / 'log.txt'
WONDERLIST_PROFILE = 'WunderList'


class MemberClicks:
    '''The get_open_requests() method queries the memberclicks website
    and retrieves all current requests.  
    Vacation requests are 'open' if the WorkDay is between the 
    DepartureDate and the ReturnDate.  
    
    Same-day requests are cutoff at 8:00 pm the previous evening.
    '''
    def __init__(self):
        self.access_token=None
        self.access_token_expires = dt.datetime.now() + dt.timedelta(days=-10)
        self.mc_date_format = "%m/%d/%Y"  # Memberclicks date format
        self.profile_search_id=None
        self.request_cutoff_hour = 20
        self.vp_request_profiles=[]
        self.vp_requests=[]
        self.wl_date_format = "%Y-%m-%d"  # WunderList date format
        self._get_credentials()
        self._create_session()
        
    def _get_credentials(self):
        '''Obtains client credentials saved in a json file.'''
        with open(str(CREDENTIALS), 'r') as fp:
            data = json.load(fp)
        self.client_id = data['MemberClicks']['client_id']
        self.client_secret = data['MemberClicks']['client_secret']
    
    def _create_session(self):
        '''Creates a new requests session'''
        self.url = 'https://dhp.memberclicks.net'
        self.client = BackendApplicationClient(client_id=self.client_id)
        self.session = OAuth2Session(client=self.client)
    
    def _get_access_token(self):
        '''Uses the client credentials to obtain an access token from 
        memberclicks.  These typically expire within one hour,
        so it is necessary to check the expiry of any previously obtained
        access token before using it.  Therefore, this will be called at the
        start of any function that interacts with memberclicks.'''
        if not self.access_token or \
        dt.datetime.fromtimestamp(self.access_token_expires) <\
        dt.datetime.now():
            auth = HTTPBasicAuth(self.client_id, self.client_secret)
            token = self.session.fetch_token(token_url=self.url +\
                                             '/oauth/v1/token', auth=auth)
            self.access_token = token['access_token']
            self.access_token_expires = token['expires_at']
            print('Access token obtained.')
    
    def _get_json(self, end_point):
        self._get_access_token()
        url = self.url + end_point
        return self.session.get(url=url).json()

    def profiles_to_json(self):
        profiles = []
        for profile in self.vp_request_profiles:
            profiles.append({'profile_id' : profile['[Profile ID]'],
                             'address' : profile['[Address | Primary | Line 1]'] \
                             + ' ' + profile['[Address | Primary | Line 2]'],
                             'contact_name' : profile['[Contact Name]'],
                             'email_primary' : profile['[Email | Primary]'],
                             'phone_primary' : profile['[Phone | Primary]'],
                             'phone_cell' : profile['[Phone | Cell]'],
                             'vp_request_alias' : profile['Vacation Patrol Request Alias'],
                             'vp_departure_date' : profile['Vacation Patrol Request Departure Date'],
                             'vp_departure_time' : profile['Vacation Patrol Request Departure Time'],
                             'vp_return_date' : profile['Vacation Patrol Request Return Date'],
                             'vp_return_time' : profile['Vacation Patrol Request Return Time'],
                             'vp_notes' : profile['Vacation Patrol Request Departure Date'],
                             'status' : 'Active', 
                             'wl_task_ids' : []})
        with open('vacation_patrol_requests.json', 'w') as fp:
            json.dump(profiles, fp)
            

    def _get_patrol_date(self):
        current_hour = dt.datetime.now().hour
        patrol_date = dt.datetime.now().date() + dt.timedelta(current_hour \
                                     >= self.request_cutoff_hour)
        return patrol_date


    def get_open_requests(self, patrol_date=None):
        '''The memberclicks api provides the ability to query members' 
        profiles.  This is a two-part process.
        1. Submit a POST request containing the query definition and 
        receive a search_id.
        2. Submit a GET request containing the serach_id and receive
        the search results.
        
        Results are stored in self.vp_requests,
        but the method returns parsed results which are pre-processed for
        the sync process.
        '''
        patrol_date = self._get_patrol_date() if not patrol_date else patrol_date
            
        def create_search_id(patrol_date):
            print('create search')
            self._get_access_token()
            mc_patrol_date = patrol_date.strftime(self.mc_date_format)
            url = self.url + '/api/v1/profile/search'
            filter_def = {'Vacation Patrol Request Departure Date': \
                    {"startDate": "01/01/2019", "endDate": mc_patrol_date},
                   'Vacation Patrol Request Return Date': \
                   {"startDate": mc_patrol_date, "endDate": "12/31/2030"}}
            response = self.session.post(url=url, json=filter_def)
            return response.json()['id']
        
        def retrieve_results(search_id):
            print('retrieve_results')
            url = self.url + '/api/v1/profile?searchId=' + search_id
            self.vp_request_profiles = []
            while True:
                response = self.session.get(url=url).json()
                for profile in response['profiles']:
                    self.vp_request_profiles.append(profile)
                if not response['nextPageUrl']:
                    break
                url = response['nextPageUrl']
        
        def parse_vp_request_profiles():
            print('parse_profiles')
            vp_requests=[]
            for profile in self.vp_request_profiles:
                address = profile['[Address | Primary | Line 1]'] \
                + ' ' + profile['[Address | Primary | Line 2]']
                address = address.strip()
                officer_notes = ['Departs: '\
                                 + profile['Vacation Patrol Request Departure Date'] \
                                 + ' ' + profile['Vacation Patrol Request Departure Time'], 
                                 'Returns: '\
                                 + profile['Vacation Patrol Request Return Date'] \
                                 + ' ' + profile['Vacation Patrol Request Return Time'], 
                                 profile['Vacation Patrol Request Special Notes to Officer']]
                wl_patrol_date = patrol_date.strftime(self.wl_date_format)
                vp_requests.append([(address, wl_patrol_date ),
                                         officer_notes])
            print('requests',len(vp_requests))
            return vp_requests

        search_id = create_search_id(patrol_date)
        retrieve_results(search_id)
        return parse_vp_request_profiles()
        
    ### Extra methods for retrieving master data, etc #########################
    def get_attributes(self, print_to_file=False):
        end_point = '/api/v1/attribute'
        attributes = self._get_json(end_point=end_point)
        if print_to_file:
            with open('dhp_attributes.json', 'w') as outfile:
                json.dump(attributes, outfile)
        return attributes
    
    def get_profiles(self):
        end_point = '/api/v1/profile'
        return self._get_json(end_point=end_point)
    
    def get_groups(self):
        end_point = '/api/v1/group'
        return self._get_json(end_point=end_point)
        
    def get_countries(self):
        end_point = '/api/v1/country'
        return self._get_json(end_point=end_point)

    def get_member_statuses(self):
        end_point = '/api/v1/member-status'
        return self._get_json(end_point=end_point)

    def get_member_types(self):
        end_point = '/api/v1/member-type'
        return self._get_json(end_point=end_point)

 

class WunderList:
    '''This class access and posts data in WunderList via the WunderList API.  
    The principal methods handle the following:
        1. Retrieve tasks from the DHP Vacation Patrol task list
        2. Retrieve assets (comments and files) from the tasks.
        3. Create new tasks in the DHP Vacation Patrol task list.
        4. Archive expired tasks by moving them to DHP VP Archive list.
    '''
    def __init__(self):
        '''create attributes such as web addresses and authentication,
        a dictionary for storing VP requests'''
        self.api = wunderpy3.WunderApi()
        self._get_credentials()
        self.client = self.api.get_client(self.access_token, self.client_id)
        
    def _get_credentials(self):
        with open(str(CREDENTIALS), 'r') as fp:
            data = json.load(fp)
        self.client_id = data[WONDERLIST_PROFILE]['client_id']
        self.client_secret = data[WONDERLIST_PROFILE]['client_secret']
        self.access_token = data[WONDERLIST_PROFILE]['access_token']
        self.list_id = int(data[WONDERLIST_PROFILE]['list_id'])
        self.archive_list_id = int(data[WONDERLIST_PROFILE]['archive_list_id'])

    def get_lists(self):
        '''Retrieves a list of all lists in the DHP Wunderlist account'''
        return self.client.get_lists()

    def get_tasks(self, list_id=None, completed=None):
        '''Retrieves open tasks from Wunderlist and stores them to wl_open_tasks'''
        list_id = self.list_id if not list_id else list_id
        if completed is None:
            tasks = self.client.get_tasks(list_id)
            for x in self.client.get_tasks(list_id, completed=True):
                tasks.append(x)
            return tasks
        return self.client.get_tasks(list_id, completed=completed)
    
    def get_task(self, task_id):
        '''Retrieves details of individual task'''
        return self.client.get_task(task_id)
        
    def post_new_task(self, title, due_date, starred=False):
        '''Posts a new task to Wunderlist'''
        response = self.client.create_task(self.list_id, 
                                             title=title[:255], 
                                             due_date=due_date, 
                                             starred=starred)
        return response    
    
    def post_new_note(self, task_id, note):
        '''Posts a note to a Wunderlist task'''
        response = self.client.create_note(task_id, note)
        return response    

    def delete_task(self, task_id):
        '''Deletes an existing task from Wunderlist'''
        revision = self.client.get_task(task_id)['revision']
        self.client.delete_task(task_id=task_id, 
                                             revision=revision)

    def get_list_comments(self, list_id=None):
        '''Retrieves comments from Wunderlist'''
        list_id = self.list_id if not list_id else list_id
        return self.client.get_list_comments(list_id)
    
    def get_task_comments(self, task_id):
        '''Retrieves open commetns from Wunderlist and stores them to wl_open_requests'''
        return self.client.get_task_comments(task_id)
    
    def get_list_files(self):
        '''Retrieves links to uploaded files from Wunderlist'''
        return self.client.get_list_files(self.list_id)

    def get_task_files(self, task_id):
        '''Retrieves files associated with a task'''
        return self.client.get_task_files(task_id)
    
    def archive_task(self, task_id, revision=None):
        '''Moves the selected task to the archive list.'''
        if not revision:
            revision = int(self.get_task(task_id=task_id)['revision'])
        else:
            revision = int(revision)
        
        return self.client.update_task(task_id=task_id, 
                                       revision=revision, 
                                       list_id=self.archive_list_id)


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

    
#vprs=VPRSync(auto_mode=True)
#vprs.sync()
#sys.exit
vprs=VPRSync()
        
#wl=WunderList()