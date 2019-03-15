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


