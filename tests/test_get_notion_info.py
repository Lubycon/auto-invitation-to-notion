from typing import Dict
from auto_invitation_to_notion.main import get_notion_users_info


def test_get_notion_users_info():
    import os
    from notion.client import NotionClient
    from schema import Schema, Regex, Or
    token_v2 = os.environ.get('NOTION_TOKEN', None)
    client = NotionClient(token_v2=token_v2)

    email_regex = '^[a-zA-Z0-9+-_.]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    schema = Schema({Regex(email_regex): {"name": str,
                                          "guest_page_ids": list,
                                          "authority": Or("lubycon", "mentor", "mentee", "unknown"),
                                          "uid": str}}
                    )

    assert schema.validate(get_notion_users_info(client=client))
