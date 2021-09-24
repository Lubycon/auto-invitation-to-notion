import os
from notion.client import NotionClient

LUBYCON_PRIVATE_PAGE = '4594ead1-b975-451d-a578-2ffeea6aa452'
LUBYCON_MENTOR_PAGE = '720e43a5-f572-440a-8e58-847b72359b16'
LUBYCON_HUB_PAGE = 'd3ebe34b-34af-4b2f-b984-ae1e91cff7f3'

token_v2 = os.environ.get('NOTION_TOKEN', None)
client = NotionClient(token_v2=token_v2)
admin_uid = client.get_email_uid().get('lubycon@gmail.com')
response = client.post('getSpaces', {})

if response.ok:
    response_json = response.json()
    space_id = list(response_json[admin_uid]['space'].keys())[-1]
    
    response = client.post("getSubscriptionData", {
                           "spaceId": space_id, "version": "v2"})
    if response.ok:
        print(response.json())
    