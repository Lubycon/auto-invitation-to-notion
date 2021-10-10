import requests
import copy
import time
import uuid
import logging

from collections import defaultdict
from typing import List, Dict

from notion.client import NotionClient


logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=logging.INFO,
)
logger = logging.getLogger()

LUBYCON_WORKSPACE = "441e783d-7010-4e27-9202-43be3ecfa332"
LUBYCON_PRIVATE_PAGE = "4594ead1-b975-451d-a578-2ffeea6aa452"
LUBYCON_MENTOR_PAGE = "720e43a5-f572-440a-8e58-847b72359b16"
LUBYCON_HUB_PAGE = "d3ebe34b-34af-4b2f-b984-ae1e91cff7f3"
LUBYCON_EMAIL = "lubycon@gmail.com"
AUTHORITY = ["admin", "mentor", "mentee", "guest"]

LUBYCON_USERS_URL = "https://raw.githubusercontent.com/Lubycon/lubycon-users/main/data/lubyconUsers-v2.json"


def get_lubycon_admin_uid(client: NotionClient) -> str:
    return client.get_email_uid().get(LUBYCON_EMAIL)


def get_workspace_id(client: NotionClient, admin_uid: str) -> str:
    response = client.post("getSpaces", {})
    response.raise_for_status()

    workspace_id = list(response.json()[admin_uid]["space"].keys())[-1]
    return workspace_id


def get_uid_pageids_assigned_users(client: NotionClient, workspace_id: str) -> Dict:
    response = client.post(
        "getSubscriptionData", {"spaceId": workspace_id, "version": "v2"}
    )
    response.raise_for_status()

    users_info = response.json()["users"]

    uid_pageids_info = {}
    for user_info in users_info:
        uid_pageids_info[user_info["userId"]] = {
            "guest_page_ids": user_info.get("guestPageIds") or []
        }

    return uid_pageids_info


def detect_authority(user_info: Dict) -> Dict:
    user_info = copy.deepcopy(user_info)
    user_uids = user_info.keys()
    for user_uid in user_uids:
        user_info[user_uid]["authority"] = "unknown"

        # TODO. 동규님 피드백 (Unresolved)
        # 앗 요기 코드가 복붙으로 증식하기 좋아보이네요 전역변수에서 loop돌릴 수 있게 해주면 코드가 깔끔해질거같아요.
        # Refer: https://github.com/Lubycon/auto-invitation-to-notion/pull/1#discussion_r718537759
        page_ids = user_info[user_uid]["guest_page_ids"]

        mentee_flag = LUBYCON_HUB_PAGE in page_ids
        mentor_flag = (LUBYCON_HUB_PAGE in page_ids) and (
            LUBYCON_MENTOR_PAGE in page_ids
        )
        lubycon_flag = (
            (LUBYCON_HUB_PAGE in page_ids)
            and (LUBYCON_MENTOR_PAGE in page_ids)
            and (LUBYCON_PRIVATE_PAGE in page_ids)
        )

        # TODO. 동규님 피드백 (Unresolved)
        # 고정 스트링은 config file로!
        # Refer: https://github.com/Lubycon/auto-invitation-to-notion/pull/1#discussion_r718538523
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
    payload = [
        {"pointer": {"table": "notion_user", "id": user_uid}, "version": -1}
        for user_uid in list(user_uid_pageids.keys())
    ]

    response = client.post("syncRecordValues", {"requests": payload})
    response.raise_for_status()

    notion_user = response.json()["recordMap"]["notion_user"]

    user_info = {}
    for user_uid in notion_user:
        v = notion_user[user_uid]["value"]
        user_info[user_uid] = {"email": v["email"], "name": v["name"]}
    return user_info


def change_pk_to_email(user_info: Dict):
    changed_user_info = {}

    for user_uid in user_info.keys():
        email = user_info[user_uid]["email"]
        name = user_info[user_uid]["name"]
        authority = user_info[user_uid]["authority"]
        guest_page_ids = user_info[user_uid]["guest_page_ids"]
        changed_user_info[email] = {
            "uid": user_uid,
            "name": name,
            "authority": authority,
            "guest_page_ids": guest_page_ids,
        }

    return changed_user_info


def get_notion_users_info(client: NotionClient):
    admin_uid = get_lubycon_admin_uid(client=client)
    workspace_uid = get_workspace_id(client=client, admin_uid=admin_uid)
    logging.info(f"workspace id: {workspace_uid}")

    user_uid_pageids = get_uid_pageids_assigned_users(
        client=client, workspace_id=workspace_uid
    )
    user_email_name = get_email_name_assigned_users(
        client=client, user_uid_pageids=user_uid_pageids
    )

    user_info = defaultdict(dict)
    for user_uid in user_uid_pageids:
        user_info[user_uid].update(user_uid_pageids[user_uid])
        user_info[user_uid].update(user_email_name[user_uid])
    user_info = dict(user_info)
    user_info.pop(admin_uid)  # remove admin in control user list

    user_info = detect_authority(user_info=user_info)
    user_info = change_pk_to_email(user_info=user_info)
    return user_info


def invite_to_notion(client: NotionClient, email: str, workspace_id: str, page_id: str):
    default_permission = "read_and_write"

    finduser_payload = {"email": email}
    response = client.post("findUser", finduser_payload)
    logger.info(">>> request findUser")
    response.raise_for_status()

    finduser_res = response.json()
    logger.info(f"findUser response: {finduser_res}")

    new_user_version: int = finduser_res.get("value").get("value").get("version")
    new_user_id: str = finduser_res.get("value").get("value").get("id")
    new_user_role: str = finduser_res.get("value").get("role")
    logger.info(f"new user id: {new_user_id}")
    logger.info(f"new user id: {new_user_version}")
    logger.info(f"new user id: {new_user_role}")

    if new_user_version == 1:  # 기존 Notion User가 아닌 경우
        logger.info(">>> Not notion user")

        createemailuser_payload = {
            "email": email,
            "preferredLocaleOrigin": "inferred_from_inviter",
            "preferredLocale": "en-US",
            "productId": "prod_CpavZFCbxF2YGx",
        }

        response = client.post("createEmailUser", createemailuser_payload)
        logger.info(">>> request createEmailUser")
        response.raise_for_status()
        logger.info(f">>> response of createEmailUser: {response.json()}")

        savetransactions_payload = {
            "requestId": str(uuid.uuid4()),
            "transactions": [
                {
                    "id": str(uuid.uuid4()),
                    "spaceId": workspace_id,
                    "operations": [
                        {
                            "pointer": {
                                "table": "block",
                                "id": page_id,
                                "spaceId": workspace_id,
                            },
                            "command": "setPermissionItem",
                            "path": ["permissions"],
                            "args": {
                                "type": "user_permission",
                                "role": default_permission,
                                "user_id": new_user_id,
                            },
                        }
                    ],
                }
            ],
        }
        response = client.post("saveTransactions", savetransactions_payload)
        logger.info(">>> request saveTransactions")
        response.raise_for_status()
        logger.info(f">>> response of saveTransactions: {response.json()}")

    elif new_user_version == 4:  # 기존 Notion User
        logger.info(">>> Notion user")
        syncrecordvalues_payload = {
            "requests": [
                {
                    "pointer": {
                        "table": "notion_user",
                        "id": new_user_id,
                    },
                    "version": -1,
                }
            ]
        }
        response = client.post("syncRecordValues", syncrecordvalues_payload)
        logger.info(">>> request syncRecordValues")
        response.raise_for_status()
        logger.info(f">>> response of syncRecordValues: {response.json()}")

        savetransactions_payload = {
            "requestId": str(uuid.uuid4()),
            "transactions": [
                {
                    "id": str(uuid.uuid4()),
                    "spaceId": workspace_id,
                    "operations": [
                        {
                            "pointer": {
                                "table": "block",
                                "id": page_id,
                                "spaceId": workspace_id,
                            },
                            "command": "setPermissionItem",
                            "path": ["permissions"],
                            "args": {
                                "type": "user_permission",
                                "role": default_permission,
                                "user_id": new_user_id,
                            },
                        },
                        {
                            "pointer": {
                                "table": "block",
                                "id": page_id,
                                "spaceId": workspace_id,
                            },
                            "path": ["last_edited_time"],
                            "command": "set",
                            "args": int(time.time()) * 1000,
                        },
                    ],
                }
            ],
        }
        response = client.post("saveTransactions", savetransactions_payload)
        logger.info(">>> request saveTransactions")
        response.raise_for_status()
        logger.info(f">>> response of saveTransactions: {response.json()}")

    else:
        raise Exception("Error in invitation Method. can't recognize user type")

    logger.info(f">>> Finished invitation - {email}")


def change_authority(
    client: NotionClient, user_id: str, to: str, workspace_id: str, page_id: str
):
    """
    editor / read_and_write / comment_only/ reader 중에서 변경하고 싶은 것인데,
    실은 일괄되게 `read_and_write` 권한으로 어느 page_id을 볼 수 있게 해주는 것이 우리의 permission의 본질이지 않을까?
    """
    default_permission = "read_and_write"
    savetransactions_payload = {
        "requestId": str(uuid.uuid4()),
        "transactions": [
            {
                "id": str(uuid.uuid4()),
                "spaceId": workspace_id,
                "operations": [
                    {
                        "pointer": {
                            "table": "block",
                            "id": page_id,
                            "spaceId": workspace_id,
                        },
                        "command": "setPermissionItem",
                        "path": ["permissions"],
                        "args": {
                            "role": to,  # editor / read_and_write / comment_only/ reader
                            "type": "user_permission",
                            "user_id": user_id,
                        },
                    },
                    {
                        "pointer": {
                            "table": "block",
                            "id": page_id,  # page_id
                            "spaceId": workspace_id,  # space_id
                        },
                        "path": ["last_edited_time"],
                        "command": "set",
                        "args": int(time.time()) * 1000,
                    },
                ],
            }
        ],
    }
    response = client.post("saveTransactions", savetransactions_payload)
    logger.info(">>> request saveTransactions")
    response.raise_for_status()
    logger.info(f">>> response of saveTransactions: {response.json()}")


def remove_to_notion():
    pass


if __name__ == "__main__":
    import os
    from notion.client import NotionClient

    token_v2 = os.environ.get("NOTION_TOKEN", None)
    client = NotionClient(token_v2=token_v2)

    lubycon_users_info = requests.get(LUBYCON_USERS_URL).json()
    notion_user_info = get_notion_users_info(client=client)

    invitation_list = []
    authority_change_list = []
    remove_list = list(notion_user_info.keys())
    for lubycon_user in lubycon_users_info:
        lubycon_user_email = lubycon_user.get("notion_email")
        lubycon_user_authority = lubycon_user.get("authority")
        lubycon_user_is_activate = lubycon_user.get("activate")

        notion_user = notion_user_info.get(lubycon_user_email)
        if not notion_user:  # Lubycon원장에는 있지만, Notion에 등록되어있지 않은 경우
            invitation_list.append(lubycon_user_email)
            continue

        if (
            notion_user.get("authority") != lubycon_user_authority
        ):  # Lubycon 원장에 적힌 권한과 Notion의 권한이 다를 경우
            authority_change_list.append(
                {
                    "email": lubycon_user_email,
                    "authority": lubycon_user_authority,
                    "uid": notion_user.get("uid"),
                }
            )

        remove_list.pop(remove_list.index(lubycon_user_email))
        if not lubycon_user_is_activate:
            remove_list.pop(remove_list.index(lubycon_user_email))

    logger.info(f"Invitation list: {invitation_list}\n")
    logger.info(f"Authorith change list: {authority_change_list}\n")
    logger.info(f"Remove list: {remove_list}\n")

    invite_to_notion(
        client=client,
        email="[email]",
        workspace_id=LUBYCON_WORKSPACE,
        page_id=LUBYCON_HUB_PAGE,
    )

    change_authority(
        client=client,
        user_id="[user_id]",
        to="reader",  # editor / read_and_write / comment_only/ reader
        workspace_id=LUBYCON_WORKSPACE,
        page_id=LUBYCON_HUB_PAGE,
    )
