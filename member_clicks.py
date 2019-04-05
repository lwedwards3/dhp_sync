'''Methods:

================= TO DO ======================================================
Merge _parse_request_profiles and _parse_officer_notes.  This should be a single function

create get_matchine_addresses

create get_all_profiles

create get_member_profile
===============================================================================

1. get_open_requests()
    Returns profiles containing current vacation patrol requests.

2. get_matching_addresses(address)
    Returns profiles matching the provided address.

3. get_all_profiles()
    Returns all active profiles.

4. get_member_profile(member_id)

Supporting methods
    DONE __init__
    DONE _get_credentials
    DONE _create_session
    DONE _get_access_token
    DONE _get_search_id
    DONE _return_search_results
    DONE _request_json
    DONE _parse_officer_note
    ? _format_response
    ? _save_as_json

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
        self._set_variables()
        self._get_credentials()
        self._create_session()

    def _set_variables(self):
        self.access_token=None
        self.access_token_expires = dt.datetime.now() + dt.timedelta(days=-10)
        self.mc_date_format = "%m/%d/%Y"  # Memberclicks date format
        self.request_cutoff_hour = 23
        self.profiles=[]
        self.vp_requests=[]
        self.wl_date_format = "%Y-%m-%d"  # WunderList date format
        current_hour = dt.datetime.now().hour
        self.patrol_date = dt.datetime.now().date() + dt.timedelta(current_hour >= self.request_cutoff_hour)
        # to import old requests (test archive process)
        #self.patrol_date = dt.datetime.now().date() + dt.timedelta(days=-1)


    def get_open_requests(self):
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
        search_id = self._get_search_id()
        self.profiles = self._retrieve_search_results(search_id)
        return self._parse_request_profiles()
        

    def get_address_profiles(self, address_line_1):
        '''Query Memberclicks for profiles matching the provided address.
        Return in same format as open request serach
        '''
        search_id = self._get_search_id(address_line_1=address_line_1)
        #self.profiles = retrieve_results(search_id)
        self.profiles = self._retrieve_search_results(search_id)
        return self._parse_request_profiles()


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


    def _request_json(self, end_point):
        '''Makes a request to memberclicks api and converts the response to json'''
        self._get_access_token()
        url = self.url + end_point
        return self.session.get(url=url).json()


    def _get_search_id(self, address_line_1=None):
        '''Returns a query search id.  
        If member_address is provided, it searches for matching addresses.  
        Otherwise, searches for open vacation patrol requests.'''
        print('_get_search_id')

        mc_patrol_date = self.patrol_date.strftime(self.mc_date_format)

        if not address_line_1:
            filter_def = {'Vacation Patrol Request Departure Date': \
                    {"startDate": "01/01/2019", "endDate": mc_patrol_date},
                    'Vacation Patrol Request Return Date': \
                    {"startDate": mc_patrol_date, "endDate": "12/31/2030"}}
        else:
            filter_def = {'[Address | Primary | Line 1]' : address_line_1}

        self._get_access_token()
        url = self.url + '/api/v1/profile/search'
        response = self.session.post(url=url, json=filter_def)
        return response.json()['id']


    def _retrieve_search_results(self, search_id):
        '''Using a previously obtained search_id,
        returns a list containing all profiles returned by the search.'''
        print('retrieve_results')
        url = self.url + '/api/v1/profile?searchId=' + search_id
        profiles = []
        while True:
            response = self.session.get(url=url).json()
            for profile in response['profiles']:
                profiles.append(profile)
            if not response['nextPageUrl']:
                break
            url = response['nextPageUrl']
        return profiles
    

    def _parse_request_profiles(self):
        vp_requests=[]
        for profile in self.profiles:
            request={}
            address = profile['[Address | Primary | Line 1]'] \
            + ' ' + profile['[Address | Primary | Line 2]']
            address = address.strip()
            request['address'] = address
            request['due_date'] = self.patrol_date.strftime(self.wl_date_format)
            request['task_id'] = ''
            request['completed'] = False
            request['assets'] = []
            request['emails_sent'] = []
            request['send_email']=False
            request['member_name'] = profile['[Contact Name]']
            request['member_status'] = profile['[Member Status]']
            request['email_address'] = profile['[Email | Primary]']
            request['officer_notes'] = self._parse_officer_note(profile)
            
            vp_requests.append(request)
        print('requests',len(vp_requests))
        return vp_requests


    ### Extra methods for retrieving master data, etc #########################
    def get_attributes(self, print_to_file=False):
        end_point = '/api/v1/attribute'
        attributes = self._request_json(end_point=end_point)
        if print_to_file:
            with open('dhp_attributes.json', 'w') as outfile:
                json.dump(attributes, outfile)
        return attributes
    
    def get_profiles(self):
        end_point = '/api/v1/profile'
        return self._request_json(end_point=end_point)
    
    def get_all_profiles(self):
        '''Returns a list containing all profiles.'''
        print('retrieve_all_profiles')
        url = self.url + '/api/v1/profile'
        profiles = []
        while True:
            response = self.session.get(url=url).json()
            for profile in response['profiles']:
                profiles.append(profile)
            if not response['nextPageUrl']:
                break
            url = response['nextPageUrl']
        return profiles

    def get_groups(self):
        end_point = '/api/v1/group'
        return self._request_json(end_point=end_point)
        
    def get_countries(self):
        end_point = '/api/v1/country'
        return self._request_json(end_point=end_point)

    def get_member_statuses(self):
        end_point = '/api/v1/member-status'
        return self._request_json(end_point=end_point)

    def get_member_types(self):
        end_point = '/api/v1/member-type'
        return self._request_json(end_point=end_point)

    def _parse_officer_note(self, profile):
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
                ('Emergency Contact 1- Name', 'Emerg name'),
                ('Emergency Contact 1- Phone Number', 'Emerg ph'),
                ('Emergency Contact 1- Relationship', 'Emerg relatn'),
                ('Emergency Contact 2 - Name', 'Emerg name2'),
                ('Emergency Contact 2 - Phone Number', 'Emerg ph2'),
                ('Emergency Contact 2 - Relationship', 'Emerg relatn2'),
                ('Jurisdiction - Police', 'Jurisdiction'))
        officer_note = [profile['Vacation Patrol Request Special Notes to Officer'],
                    '-----------------------------------',
                    'Departs: '+ profile['Vacation Patrol Request Departure Date'] \
                     + ' ' + profile['Vacation Patrol Request Departure Time'], 
                                 'Returns: ' + profile['Vacation Patrol Request Return Date'] \
                                 + ' ' + profile['Vacation Patrol Request Return Time'],'']
        for attr in attrs[6:]:
            val = profile[attr[0]]
            if len(str(val)) > 0:
                officer_note.append(str(attr[1]) + ': ' + str(val))
                officer_note.append('')
        return officer_note
