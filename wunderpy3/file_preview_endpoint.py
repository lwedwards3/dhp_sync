'''
Encapsulates all tasks that can be run against the 'file_preview' endpoint
'''
def get_file_preview(client, file_id):
    endpoint = '/'.join([client.api.Endpoints.FILE_PREVIEW, str(comment_id)])
    response = client.authenticated_request(endpoint)
    return response.json()

