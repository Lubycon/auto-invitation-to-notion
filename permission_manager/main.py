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

LUBYCON_ALL = "72a5f0ad-ccbc-4a2e-a7ca-a2106bea3326"
LUBYCON_PRIVATE_PAGE = "4594ead1-b975-451d-a578-2ffeea6aa452"
LUBYCON_MATE_PAGE = "720e43a5-f572-440a-8e58-847b72359b16"
LUBYCON_SANDBOX_PAGE = "d3ebe34b-34af-4b2f-b984-ae1e91cff7f3"

LUBYCON_EMAIL = "lubycon@gmail.com"
AUTHORITY = ["admin", "mate", "member"]

LUBYCON_USERS_URL = "https://raw.githubusercontent.com/Lubycon/lubycon-users/main/data/lubyconUsers-v2.json"


def get_lubycon_admin_uid(client: NotionClient) -> str:
    return client.get_email_uid().get(LUBYCON_EMAIL)


def get_workspace_id(client: NotionClient, admin_uid: str) -> str:
    logger.info(f"getting workspace id")
    response = client.post("getSpaces", {})
    response.raise_for_status()

    workspace_id = list(response.json()[admin_uid]["space"].keys())[-1]
    logger.info(f"Finished workspace id")
    logger.info(f"===============================\n")
    return workspace_id


def get_uid_pageids_assigned_users(client: NotionClient, workspace_id: str) -> Dict:
    logger.info(f"getting user's uid and page ids assigned to notion")
    response = client.post(
        "getSubscriptionData", {"spaceId": workspace_id, "version": "v2"}
    )
    response.raise_for_status()
    logger.info(f"reponse of getSubscriptionData - {response.json()}")
    users_info = response.json()["users"]

    uid_pageids_info = {}
    for user_info in users_info:
        uid_pageids_info[user_info["userId"]] = {
            "guest_page_ids": user_info.get("guestPageIds") or []
        }

    logger.info(f"Finished getting user's uid and page ids assigned to notion")
    logger.info(f"===============================\n")
    return uid_pageids_info


def detect_authority(user_info: Dict) -> Dict:
    logger.info(f"Detecting user authority")
    user_info = copy.deepcopy(user_info)
    user_uids = user_info.keys()
    for user_uid in user_uids:
        user_info[user_uid]["authority"] = "unknown"

        # TODO. 동규님 피드백 (Unresolved)
        # 앗 요기 코드가 복붙으로 증식하기 좋아보이네요 전역변수에서 loop돌릴 수 있게 해주면 코드가 깔끔해질거같아요.
        # Refer: https://github.com/Lubycon/auto-invitation-to-notion/pull/1#discussion_r718537759
        page_ids = user_info[user_uid]["guest_page_ids"]

        member_flag = page_ids == [LUBYCON_SANDBOX_PAGE]
        mate_flag = set(page_ids) == {LUBYCON_SANDBOX_PAGE, LUBYCON_MATE_PAGE}
        admin_flag = set(page_ids) == {LUBYCON_ALL}

        # TODO. 동규님 피드백 (Unresolved)
        # 고정 스트링은 config file로!
        # Refer: https://github.com/Lubycon/auto-invitation-to-notion/pull/1#discussion_r718538523
        if admin_flag:
            user_info[user_uid]["authority"] = "admin"
            continue

        if mate_flag:
            user_info[user_uid]["authority"] = "mate"
            continue

        if member_flag:
            user_info[user_uid]["authority"] = "member"
            continue
    logger.info(f"Finished getting user authority")
    logger.info(f"===============================\n")
    return user_info


def get_email_name_assigned_users(client: NotionClient, user_uid_pageids: List[str]):
    logger.info(f"Get user's email and name from notion")
    payload = [
        {"pointer": {"table": "notion_user", "id": user_uid}, "version": -1}
        for user_uid in list(user_uid_pageids.keys())
    ]

    response = client.post("syncRecordValues", {"requests": payload})
    response.raise_for_status()
    logger.info(f"response of syncRecordValues - {response.json()}")

    notion_user = response.json()["recordMap"]["notion_user"]

    user_info = {}
    logger.info("notion_user: {notion_user}")

    for user_uid in notion_user:
        v = notion_user.get(user_uid).get("value")
        user_info[user_uid] = {"email": v.get("email"), "name": v.get("name")}

    logger.info(f"Finished getting user's email and name from notion")
    logger.info(f"===============================\n")
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
    logger.info(f">>> Get notion user info")
    admin_uid = get_lubycon_admin_uid(client=client)
    workspace_uid = get_workspace_id(client=client, admin_uid=admin_uid)
    logger.info(f">>> workspace id: {workspace_uid}")

    user_uid_pageids = get_uid_pageids_assigned_users(
        client=client, workspace_id=workspace_uid
    )
    logger.info(f">>> user_uid_pageids: {user_uid_pageids}\n")
    user_email_name = get_email_name_assigned_users(
        client=client, user_uid_pageids=user_uid_pageids
    )
    logger.info(f">>> user_email_name: {user_email_name}\n")

    user_info = defaultdict(dict)
    for user_uid in user_uid_pageids:
        user_info[user_uid].update(user_uid_pageids[user_uid])
        user_info[user_uid].update(user_email_name[user_uid])
    user_info = dict(user_info)
    user_info.pop(admin_uid)  # remove admin in control user list

    user_info = detect_authority(user_info=user_info)
    user_info = change_pk_to_email(user_info=user_info)
    logger.info(f">>> Finished getting notion user info")
    logger.info(f"===============================\n")
    return user_info


def invite_to_notion(client: NotionClient, email: str, workspace_id: str, page_id: str):
    logger.info(f">>> Invite User - {email}")
    default_permission = "read_and_write"

    finduser_payload = {"email": email}
    response = client.post("findUser", finduser_payload)
    response.raise_for_status()

    finduser_res = response.json()
    logger.info(f">>> response of findUser: {finduser_res}")

    given_name: int = finduser_res.get("value").get("value").get("given_name")
    new_user_id: str = finduser_res.get("value").get("value").get("id")

    if not given_name:  # 기존 Notion User가 아닌 경우
        logger.info(f">>> Not notion user")
        createemailuser_payload = {
            "email": email,
            "preferredLocaleOrigin": "inferred_from_inviter",
            "preferredLocale": "en-US",
            "productId": "prod_CpavZFCbxF2YGx",
        }

        response = client.post("createEmailUser", createemailuser_payload)
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
        response.raise_for_status()
        logger.info(f">>> response of saveTransactions: {response.json()}")

    elif given_name:  # 기존 Notion User
        logger.info(f">>> notion user")
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
        response.raise_for_status()
        logger.info(f">>> response of saveTransactions: {response.json()}")

    else:
        raise Exception("Error in invitation Method. can't recognize user type")

    logger.info(f">>> Finished invite user - {email}")
    logger.info(f"===============================\n")


def change_permission(
    client: NotionClient, user_id: str, to: str, workspace_id: str, page_id: str
):
    """
    editor / read_and_write / comment_only/ reader 중에서 변경하고 싶은 것인데,
    실은 일괄되게 `read_and_write` 권한으로 어느 page_id을 볼 수 있게 해주는 것이 우리의 permission의 본질이지 않을까?
    """
    logger.info(f">>> Change authority")
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
    response.raise_for_status()
    logger.info(f">>> response of saveTransactions: {response.json()}")
    logger.info(f">>> Finished change authority")
    logger.info(f"===============================\n")


def remove_from_notion(client: NotionClient, user_id: str, workspace_id: str):
    logger.info(f">>> Remove user from notion")
    remove_users_from_space_payload = {
        "userIds": [user_id],
        "spaceId": workspace_id,
        "removePagePermissions": True,
        "revokeUserTokens": False,
    }
    response = client.post("removeUsersFromSpace", remove_users_from_space_payload)
    logger.info(f">>> request removeUsersFromSpace: {response.json()}")
    response.raise_for_status()
    logger.info(f">>> Finished remove user from notion: {user_id}")
    logger.info(f"===============================\n")


def change_authority(
    client: NotionClient, email: str, user_id: str, workspace_id: str, authority: str
):
    remove_from_notion(client=client, user_id=user_id, workspace_id=workspace_id)

    page_ids = []
    if authority == "admin":
        page_ids = [LUBYCON_ALL]
    elif authority == "mate":
        page_ids = [LUBYCON_MATE_PAGE, LUBYCON_SANDBOX_PAGE]
    elif authority == "member":
        page_ids = [LUBYCON_SANDBOX_PAGE]
    else:
        logger.error(">>> Wrong Authority")

    for page_id in page_ids:
        invite_to_notion(
            client=client,
            email=email,
            workspace_id=LUBYCON_WORKSPACE,
            page_id=page_id,
        )


if __name__ == "__main__":
    import os
    from notion.client import NotionClient

    notion_token = os.environ.get("NOTION_TOKEN", None)
    github_token = os.environ.get("LUBYCON_GITHUB_TOKEN", None)
    client = NotionClient(token_v2=notion_token)

    header = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3.raw",
    }
    response = requests.get(LUBYCON_USERS_URL, headers=header)
    response.raise_for_status()
    lubycon_users_info = response.json()

    notion_user_info = get_notion_users_info(client=client)
    logging.info(f">>> Notion user info : {notion_user_info}\n")
    invitation_list = []
    authority_change_list = []
    remove_email_list = list(notion_user_info.keys())
    for lubycon_user in lubycon_users_info:
        lubycon_user_email = lubycon_user.get("notion_email")
        lubycon_user_authority = lubycon_user.get("authority")
        lubycon_user_is_activate = lubycon_user.get("activate")

        notion_user = notion_user_info.get(lubycon_user_email)
        if not notion_user:  # Lubycon원장에는 있지만, Notion에 등록되어있지 않은 경우
            if lubycon_user_is_activate:
                invitation_list.append(
                    {
                        "email": lubycon_user_email,
                        "authority": lubycon_user_authority,
                        "activate": lubycon_user_is_activate,
                    }
                )
            continue

        if (
            notion_user.get("authority") != lubycon_user_authority
        ):  # Lubycon 원장에 적힌 권한과 Notion의 권한이 다를 경우
            authority_change_list.append(
                {
                    "email": lubycon_user_email,
                    "uid": notion_user.get("uid"),
                    "current": notion_user.get("authority"),
                    "to": lubycon_user_authority,
                }
            )

        remove_email_list.pop(remove_email_list.index(lubycon_user_email))
        if not lubycon_user_is_activate:
            if lubycon_user_email in remove_email_list:
                remove_email_list.pop(remove_email_list.index(lubycon_user_email))

    remove_user_list = []
    for remove_user_email in remove_email_list:
        remove_user_list.append(
            {
                "email": remove_user_email,
                "uid": notion_user_info.get(remove_user_email).get("uid"),
                "name": notion_user_info.get(remove_user_email).get("name"),
            }
        )
    logger.info(f">>> Invitation list: {invitation_list}\n")
    logger.info(f">>> Authorith change list: {authority_change_list}\n")
    logger.info(f">>> Remove list: {remove_user_list}\n")

    # Invite
    for invite_user in invitation_list:
        email = invite_user.get("email")
        authority = invite_user.get("authority")
        is_activate = invite_user.get("activate")

        if not is_activate:
            continue

        page_ids = []
        if authority == "admin":
            page_ids = [LUBYCON_ALL]

        elif authority == "mate":
            page_ids = [LUBYCON_MATE_PAGE, LUBYCON_SANDBOX_PAGE]

        elif authority == "member":
            page_ids = [LUBYCON_SANDBOX_PAGE]

        for page_id in page_ids:
            invite_to_notion(
                client=client,
                email=email,
                workspace_id=LUBYCON_WORKSPACE,
                page_id=page_id,
            )

    for authority_changed_user in authority_change_list:
        email = authority_changed_user.get("email")
        authority = authority_changed_user.get("to")
        user_id = authority_changed_user.get("uid")
        workspace_id = LUBYCON_WORKSPACE

        change_authority(
            client=client,
            email=email,
            user_id=user_id,
            workspace_id=workspace_id,
            authority=authority,
        )

    for remove_user in remove_user_list:
        remove_from_notion(
            client=client,
            user_id=remove_user.get("uid"),
            workspace_id=LUBYCON_WORKSPACE,
        )
