'''
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

import json
from pathlib import Path
import wunderpy3


class WunderList:
    '''This class access and posts data in WunderList via the WunderList API.  
    The principal methods handle the following:
        1. Retrieve tasks from the DHP Vacation Patrol task list
        2. Retrieve assets (comments and files) from the tasks.
        3. Create new tasks in the DHP Vacation Patrol task list.
        4. Archive expired tasks by moving them to DHP VP Archive list.
    '''
    def __init__(self, test_mode=False):
        '''create attributes such as web addresses and authentication,
        a dictionary for storing VP requests'''
        self._set_variables(test_mode)
        self.api = wunderpy3.WunderApi()
        self._get_credentials()
        self.client = self.api.get_client(self.access_token, self.client_id)
        
    
    def _set_variables(self, test_mode):
        self.credentials_file = str(Path.cwd().parent / 'creds.json')
        self.wunderlist_profile = 'WunderList'
        self.test_mode = test_mode
        if self.test_mode:
            self.wunderlist_profile = 'WunderList_test'
            

    def _get_credentials(self):
        with open(self.credentials_file, 'r') as fp:
            data = json.load(fp)
        self.client_id = data[self.wunderlist_profile]['client_id']
        self.client_secret = data[self.wunderlist_profile]['client_secret']
        self.access_token = data[self.wunderlist_profile]['access_token']
        self.list_id = int(data[self.wunderlist_profile]['list_id'])
        self.archive_list_id = int(data[self.wunderlist_profile]['archive_list_id'])

    def get_lists(self):
        '''Retrieves a list of all lists in the DHP Wunderlist account'''
        return self.client.get_lists()

    def get_tasks(self, list_id=None, completed=None):
        '''Retrieves tasks from Wunderlist and stores them to wl_open_tasks.
        By default, retrieves both complete and incomplete tasks.
        If completed=True then retrieves only incomplete tasks.'''
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

    def update_note(self, task_id, revision=None, content=None):
        '''Posts a note to a Wunderlist task'''
        if not revision:
            revision = int(self.get_task(task_id=task_id)['revision'])
        else:
            revision = int(revision)
        response = self.client.update_note(task_id, revision, content)
        return response    

    def get_note(self, task_id):
        '''Returns the note, if available'''
        note = self.client.get_task_notes(task_id=task_id)
        if type(note) == list:
            if len(note) > 0:
                return note[0]['content']
        return ''
        
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
    
    def get_file_preview(self, file_id):
        '''Retrieves a link to a file preview'''
        return self.client.get_file_preview(file_id)
    
    def archive_task(self, task_id, revision=None):
        '''Moves the selected task to the archive list.'''
        if not revision:
            revision = int(self.get_task(task_id=task_id)['revision'])
        else:
            revision = int(revision)
        
        return self.client.update_task(task_id=task_id, 
                                       revision=revision, 
                                       list_id=self.archive_list_id)


    def update_task_due_date(self, task_id, revision=None, due_date=None):
        '''Updates the due_date for the selected task.'''
        if not revision:
            revision = int(self.get_task(task_id=task_id)['revision'])
        else:
            revision = int(revision)
        return self.client.update_task(task_id=task_id, 
                                       revision=revision, 
                                       due_date=due_date)


    def update_task_title(self, task_id, revision=None, title=None):
        '''Updates the title for the selected task.'''
        if not revision:
            revision = int(self.get_task(task_id=task_id)['revision'])
        else:
            revision = int(revision)
        return self.client.update_task(task_id=task_id, 
                                       revision=revision, 
                                       title=title)
