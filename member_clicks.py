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
from requests_oauthlib import OAuth2Session
from requests.auth import HTTPBasicAuth
from oauthlib.oauth2 import BackendApplicationClient

CREDENTIALS = Path.cwd().parent / 'creds.json'

class MemberClicks:
    '''The get_open_requests() method queries the memberclicks website
    and retrieves all current requests.  
    Vacation requests are 'open' if the WorkDay is between the 
    DepartureDate and the ReturnDate.  
    
    New requests are added at 11:00 pm the previous evening.
    '''
    def __init__(self):
        self.access_token=None
        self.access_token_expires = dt.datetime.now() + dt.timedelta(days=-10)
        self.mc_date_format = "%m/%d/%Y"  # Memberclicks date format
        self.profile_search_id=None
        self.request_cutoff_hour = 23
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
        '''Makes a request to memberclicks api and converts the response to json'''
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
            vp_requests=[]
            for profile in self.vp_request_profiles:
                request={}
                address = profile['[Address | Primary | Line 1]'] \
                + ' ' + profile['[Address | Primary | Line 2]']
                address = address.strip()
                request['address'] = address
                request['due_date'] = patrol_date.strftime(self.wl_date_format)
                request['officer_notes'] = self.profile_info(profile)
                request['member_name'] = profile['[Contact Name]']
                request['email_address'] = profile['[Email | Primary]']
                request['task_id'] = ''
                request['completed'] = ''
                request['assets'] = []
                request['send_email']=False
                
                vp_requests.append(request)
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

    def profile_info(self, profile):
        attrs = (('Vacation Patrol Request Special Notes to Officer', 'VP Note'),
                ('Vacation Patrol Request Departure Date', 'Depart date'),
                ('Vacation Patrol Request Departure Time', 'Depart time'),
                ("Vacation Patrol Request Officer's Notes", 'Other note'),
                ('Vacation Patrol Request Return Date', 'Return date'),
                ('Vacation Patrol Request Return Time', 'Return time'),
                ('[Contact Name]', 'Contact'),
                ('[Phone | Primary]', 'Phone-prime'),
                ('[Email | Primary]', 'Email-prime'),
                ('Other Notes to Officer', 'Other notes'),
                ('Employees, caregivers or others regularly on the property', 'On property'),
                ('Pet - please describe any dogs (breed, size, name, list precautions)', 'Pets'),
                ('Renters? Please list their names and vehicle information, including color', 'Renters'),
                ('Vehicle Number 1 (make/model/year/color)', 'Vehicle1'),
                ('Vehicle Number 2 (make/model/year/color)', 'Vehicle2'),
                ('Vehicle Number 3 (make/model/year/color)', 'Vehicle3'),
                ('Vehicle Number 4 (make/model/year/color)', 'Vehicle4'),
                ('Vehicle Number 5 (make/model/year/color)', 'Vehicle5'),
                ('[Address | Primary | Line 1]', 'Addr-prime'),
                ('[Address | Primary | Line 2]', 'Addr2-prime'),
                ('[Address | to be Patrolled | Line 1]', 'Addr-patrol'),
                ('[Address | to be Patrolled | Line 2]', 'Addr-patrol'),
                ('[Phone | Cell]', 'Phone-cell'),
                ('[Phone | Home]', 'Phone-home'),
                ('[Phone | Other]', 'Phone-other'),
                ('[Phone | Work]', 'Phone-work'),
                ('[Email | Email]', 'Email'),
                ('Emergency Contact 1- Name', 'EM contact'),
                ('Emergency Contact 1- Phone Number', 'Emg contact ph'),
                ('Emergency Contact 1- Relationship', 'Emg contact rel'),
                ('Emergency Contact 2 - Name', 'Emg contact2'),
                ('Emergency Contact 2 - Phone Number', 'Emg contact2 ph'),
                ('Emergency Contact 2 - Relationship', 'Emg contact 2 rel'),
                ('Jurisdiction - Police', 'Jurisdiction'))
        note = [profile['Vacation Patrol Request Special Notes to Officer'],
                    '-----------------------------------',
                    'Departs: '+ profile['Vacation Patrol Request Departure Date'] \
                     + ' ' + profile['Vacation Patrol Request Departure Time'], 
                                 'Returns: ' + profile['Vacation Patrol Request Return Date'] \
                                 + ' ' + profile['Vacation Patrol Request Return Time'],'']
        for attr in attrs[6:]:
            val = profile[attr[0]]
            if len(str(val)) > 0:
                note.append(str(attr[1]) + ': ' + str(val))
                note.append('')
        return note

