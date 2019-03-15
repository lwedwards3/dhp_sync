'''
Encapsulates all tasks that can be run against the 'notes' endpoint
'''
def get_task_files(client, task_id):
    params = {
            'task_id' : int(task_id)
            }
    response = client.authenticated_request(client.api.Endpoints.FILES, params=params)
    assert response.status_code == 200
    return response.json()

def get_list_files(client, list_id):
    params = {
            'list_id' : int(list_id)
            }
    response = client.authenticated_request(client.api.Endpoints.FILES, params=params)
    assert response.status_code == 200
    return response.json()

def get_file(client, file_id):
    endpoint = '/'.join([client.api.Endpoints.FILES, str(comment_id)])
    response = client.authenticated_request(endpoint)
    return response.json()

