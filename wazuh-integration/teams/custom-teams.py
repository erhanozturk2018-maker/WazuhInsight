#!/usr/bin/env python3
import sys
import html
import json
import logging
import requests

logging.basicConfig(
    filename="/var/ossec/logs/integrations.log",
    level=logging.INFO,
    format="%(asctime)s custom-teams: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def main():
    alert_file = sys.argv[1]
    hook_url = html.unescape(sys.argv[3])
    logging.info(f"ALINAN HOOK_URL: {hook_url}")
    with open(alert_file) as f:
        alert = json.load(f)

    rule = alert.get("rule", {})
    agent = alert.get("agent", {})

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": f"Wazuh Alert - Level {rule.get('level')}",
                     "weight": "bolder", "size": "medium"},
                    {"type": "TextBlock", "text": rule.get("description", ""), "wrap": True},
                    {"type": "FactSet", "facts": [
                        {"title": "Agent", "value": agent.get("name", "")},
                        {"title": "Rule ID", "value": str(rule.get("id", ""))},
                        {"title": "Timestamp", "value": alert.get("timestamp", "")},
                    ]}
                ]
            }
        }]
    }

    try:
        r = requests.post(hook_url, json=payload, timeout=10)
        logging.info(f"gonderildi, HTTP durum kodu={r.status_code}")
    except Exception as e:
        logging.error(f"HATA: istek gonderilemedi - {e}")

if __name__ == "__main__":
    main()
