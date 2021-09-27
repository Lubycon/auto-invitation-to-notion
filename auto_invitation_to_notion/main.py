import requests
import copy
from collections import defaultdict
from typing import List, Dict

from notion.client import NotionClient


LUBYCON_PRIVATE_PAGE = '4594ead1-b975-451d-a578-2ffeea6aa452'
LUBYCON_MENTOR_PAGE = '720e43a5-f572-440a-8e58-847b72359b16'
LUBYCON_HUB_PAGE = 'd3ebe34b-34af-4b2f-b984-ae1e91cff7f3'


def get_lubycon_admin_uid(client: NotionClient) -> str:
    return client.get_email_uid().get('lubycon@gmail.com')


def get_workspace_id(client: NotionClient, admin_uid: str) -> str:
    response = client.post('getSpaces', {})

    if not response.ok:
        raise Exception(handle_request_error(response=response))

    workspace_id = list(response.json()[admin_uid]['space'].keys())[-1]
    return workspace_id


def handle_request_error(response: requests.Response) -> str:
    return f"request fail!. status code: {response.status_code}, detail: {response.text}"


def get_uid_pageids_assigned_users(client: NotionClient, workspace_id: str) -> Dict:
    response = client.post("getSubscriptionData", {
                           "spaceId": workspace_id, "version": "v2"})

    if not response.ok:
        raise Exception(handle_request_error(response=response))

    users_info = response.json()["users"]

    answer = {}
    for user_info in users_info:
        answer[user_info["userId"]] = {
            "guest_page_ids": user_info.get("guestPageIds") or []}

    return answer


def detect_authority(user_info: Dict) -> Dict:
    user_info = copy.deepcopy(user_info)
    user_uids = user_info.keys()
    for user_uid in user_uids:
        user_info[user_uid]["authority"] = "unknown"

        page_ids = user_info[user_uid]["guest_page_ids"]

        mentee_flag = LUBYCON_HUB_PAGE in page_ids
        mentor_flag = (LUBYCON_HUB_PAGE in page_ids) and (
            LUBYCON_MENTOR_PAGE in page_ids)
        lubycon_flag = (LUBYCON_HUB_PAGE in page_ids) and (
            LUBYCON_MENTOR_PAGE in page_ids) and (LUBYCON_PRIVATE_PAGE in page_ids)

        if lubycon_flag:
            user_info[user_uid]["authority"] = "lubycon"
            continue

        if mentor_flag:
            user_info[user_uid]["authority"] = "mentor"
            continue

        if mentee_flag:
            user_info[user_uid]["authority"] = "mentee"
            continue

    return user_info


def get_email_name_assigned_users(client: NotionClient, user_uid_pageids: List[str]):
    payload = [{"pointer": {"table": "notion_user",
                            "id": user_uid},
                "version": -1} for user_uid in list(user_uid_pageids.keys())]

    response = client.post("syncRecordValues", {"requests": payload})
    if not response.ok:
        raise Exception(handle_request_error(response=response))

    notion_user = response.json()["recordMap"]["notion_user"]

    ans = {}
    for user_uid in notion_user:
        v = notion_user[user_uid]["value"]
        ans[user_uid] = {"email": v["email"], "name": v["name"]}
    return ans


def change_pk_to_email(user_info: Dict):
    ans = {}

    for user_uid in user_info.keys():
        email = user_info[user_uid]["email"]
        name = user_info[user_uid]["name"]
        authority = user_info[user_uid]["authority"]
        guest_page_ids = user_info[user_uid]["guest_page_ids"]
        ans[email] = {"uid": user_uid, "name": name,
                      "authority": authority, "guest_page_ids": guest_page_ids}

    return ans


def get_notion_users_info(client: NotionClient):
    admin_uid = get_lubycon_admin_uid(client=client)
    workspace_uid = get_workspace_id(client=client, admin_uid=admin_uid)
    user_uid_pageids = get_uid_pageids_assigned_users(
        client=client, workspace_id=workspace_uid)
    user_email_name = get_email_name_assigned_users(
        client=client, user_uid_pageids=user_uid_pageids)

    user_info = defaultdict(dict)
    for user_uid in user_uid_pageids:
        user_info[user_uid].update(user_uid_pageids[user_uid])
        user_info[user_uid].update(user_email_name[user_uid])
    user_info = dict(user_info)
    user_info.pop(admin_uid)  # remove admin in control user list

    user_info = detect_authority(user_info=user_info)
    user_info = change_pk_to_email(user_info=user_info)
    return user_info
