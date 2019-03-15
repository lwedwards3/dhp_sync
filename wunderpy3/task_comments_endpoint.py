'''
Encapsulates all tasks that can be run against the 'notes' endpoint
'''
def get_task_comments(client, task_id):
    params = {
            'task_id' : int(task_id)
            }
    response = client.authenticated_request(client.api.Endpoints.TASK_COMMENTS, params=params)
    assert response.status_code == 200
    return response.json()

def get_list_comments(client, list_id):
    params = {
            'list_id' : int(list_id)
            }
    response = client.authenticated_request(client.api.Endpoints.TASK_COMMENTS, params=params)
    assert response.status_code == 200
    return response.json()

def get_task_comment(client, comment_id):
    endpoint = '/'.join([client.api.Endpoints.TASK_COMMENTS, str(comment_id)])
    response = client.authenticated_request(endpoint)
    return response.json()

def create_comment(client, task_id, text):
    data = {
            'task_id' : int(task_id),
            'text' : text,
            }
    response = client.authenticated_request(client.api.Endpoints.TASK_COMMENTS, method='POST', data=data)
    return response.json()

