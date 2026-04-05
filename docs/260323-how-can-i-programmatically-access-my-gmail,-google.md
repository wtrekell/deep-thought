<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# How can I programmatically access my Gmail, Google Calendar, and possibly other services I use from Google with python?

You use Google’s Python client libraries plus OAuth2: create a Google Cloud project, enable the APIs (Gmail, Calendar, etc.), download OAuth credentials, then use the same auth flow and client to call each service from Python.[^1_1][^1_2][^1_3][^1_4][^1_5]

## Big picture

- Install the core libraries:
`pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib`.[^1_3][^1_4][^1_5]
- In Google Cloud Console, create a project, enable Gmail API, Google Calendar API, and any other Workspace / Google APIs you want to call.[^1_2][^1_1]
- Create an OAuth 2.0 **Desktop app** credential, download `credentials.json` into your project folder.[^1_1][^1_2]
- In Python, run an “installed app” OAuth flow once; it opens a browser, you log in and approve; tokens are stored in `token.json` so you can reuse them.[^1_2][^1_1]


## Shared auth pattern in Python

This pattern is the same for Gmail, Calendar, Drive, etc.; you just change **SCOPES** and the service name/version.[^1_3][^1_1][^1_2]

```python
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Add scopes for every API you want to use
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    # e.g. Drive: "https://www.googleapis.com/auth/drive.readonly",
]

def get_creds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def main():
    creds = get_creds()

    # Gmail service
    gmail = build("gmail", "v1", credentials=creds)
    # Calendar service
    calendar = build("calendar", "v3", credentials=creds)

    # Example Gmail: list labels
    labels_resp = gmail.users().labels().list(userId="me").execute()
    for label in labels_resp.get("labels", []):
        print("Label:", label["name"])

    # Example Calendar: next 10 events
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    events_resp = calendar.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    for event in events_resp.get("items", []):
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, "-", event.get("summary"))

if __name__ == "__main__":
    main()
```

The Gmail and Calendar quickstart samples use this same approach and just vary the scope and the API calls.[^1_1][^1_2]

## Common Google services and scopes

| Service | API ID | Typical scope example |
| :-- | :-- | :-- |
| Gmail | `gmail` | `https://www.googleapis.com/auth/gmail.readonly`[^1_1] |
| Google Calendar | `calendar` | `https://www.googleapis.com/auth/calendar.readonly`[^1_2] |
| Google Drive | `drive` | `https://www.googleapis.com/auth/drive.readonly`[^1_3] |
| People API | `people` | `https://www.googleapis.com/auth/contacts.readonly`[^1_3] |

All of them are used with `build("service_name", "vX", credentials=creds)` from the same client library.[^1_4][^1_5][^1_3]

## Next step: what you want to build

Do you mainly want to read data (emails, events) or also send emails / create calendar events from Python?
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://developers.google.com/workspace/gmail/api/quickstart/python

[^1_2]: https://developers.google.com/workspace/calendar/api/quickstart/python

[^1_3]: https://ftp.broadwayinfosys.com/blog/python-google-api-simplified-guide-and-client-library-1767647990

[^1_4]: https://github.com/googleapis/google-api-python-client

[^1_5]: https://pypi.org/project/google-api-python-client/

[^1_6]: https://stackoverflow.com/questions/73584575/gmail-api-with-python

[^1_7]: https://behainguyen.wordpress.com/2022/05/09/gmail-api-quick-start-with-python-and-nodejs/

[^1_8]: https://github.com/googleworkspace/python-samples/blob/main/gmail/quickstart/quickstart.py

[^1_9]: https://www.reddit.com/r/pythontips/comments/1pbdoch/python_to_read_mail_from_gmail_using_google_api/

[^1_10]: https://www.youtube.com/watch?v=7X3fBlMw_1k

[^1_11]: https://stackoverflow.com/questions/31437541/using-google-calendar-api-with-an-api-key-python

[^1_12]: https://www.pythonanywhere.com/forums/topic/28606/

[^1_13]: https://github.com/alexandrumd/google-calendar-quickstart

[^1_14]: https://www.youtube.com/watch?v=p7cn1n1kx3I

[^1_15]: https://www.youtube.com/watch?v=1JkKtGFnua8


---

# I need full sync with Gmail Calendar and Drive

To get “full sync” you request broader scopes for each API, then use the same credentials object to read, create, update, and delete Gmail messages/labels, Calendar events, and Drive files from Python.[^2_1][^2_2][^2_3][^2_4][^2_5]

## Scopes you’ll need

Use the smallest powerful scopes that still let you sync in both directions.

- Gmail:
    - Full mailbox access (read, send, delete, labels): `https://mail.google.com/` or
“read, compose, send, and modify”: `https://www.googleapis.com/auth/gmail.modify`.[^2_6][^2_7][^2_8][^2_1]
- Calendar (full control of all calendars you can see):
    - `https://www.googleapis.com/auth/calendar`.[^2_9][^2_2][^2_10][^2_11]
- Drive (upload, download, move, delete, organize):
    - Full Drive: `https://www.googleapis.com/auth/drive`.[^2_3][^2_4][^2_5]

Example consolidated scopes list:

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
]
```

If you change scopes after first login, delete `token.json` so the consent screen reappears with the new permissions.[^2_5][^2_12][^2_13]

## One auth, three services

Reusing the same pattern from before, you authenticate once and build per‑service clients.[^2_4][^2_12][^2_13][^2_3][^2_5]

```python
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os.path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
]

def get_creds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

creds = get_creds()
gmail = build("gmail", "v1", credentials=creds)
calendar = build("calendar", "v3", credentials=creds)
drive = build("drive", "v3", credentials=creds)
```

Now `gmail`, `calendar`, and `drive` can all perform read/write operations in your account.[^2_2][^2_6][^2_3][^2_4]

## Example sync-style operations

These are the core building blocks for a “full sync” loop.

- Gmail (list, label, send, delete):
    - List messages: `gmail.users().messages().list(userId="me").execute()`.[^2_12][^2_6]
    - Modify labels: `users().messages().modify(..., body={"addLabelIds":[...], "removeLabelIds":[...]})`.[^2_6]
    - With `gmail.modify` or `mail.google.com` you can send drafts and delete messages.[^2_8][^2_1][^2_6]
- Calendar (upsert events):
    - List events: `calendar.events().list(calendarId="primary", ...)`.
    - Create: `calendar.events().insert(calendarId="primary", body=event).execute()`.
    - Update: `calendar.events().update(calendarId="primary", eventId=id, body=event).execute()`.[^2_14][^2_9][^2_2]
- Drive (files and folders):
    - List files: `drive.files().list(pageSize=100, fields="files(id,name,modifiedTime)").execute()`.[^2_3][^2_4][^2_5]
    - Upload: `drive.files().create(body=metadata, media_body=media, fields="id").execute()`.
    - Update/replace file content: `drive.files().update(fileId=id, media_body=media).execute()`.[^2_4][^2_3]


### Quick comparison of “full” scopes

| API | Scope | What it allows (short) |
| :-- | :-- | :-- |
| Gmail | `https://www.googleapis.com/auth/gmail.modify` | Read, send, modify, delete labels, but not hard-delete all.[^2_1][^2_6][^2_8] |
| Gmail | `https://mail.google.com/` | Full Gmail access including permanent deletes.[^2_1][^2_7] |
| Calendar | `https://www.googleapis.com/auth/calendar` | See, create, edit, delete calendars and events you can access.[^2_9][^2_2] |
| Drive | `https://www.googleapis.com/auth/drive` | Full read/write on your Drive files and folders.[^2_3][^2_4][^2_5] |

## Architecture tips for “full sync”

For each resource type (email, event, file) keep local metadata so you can detect changes and push only deltas.

- Use resource IDs and timestamps (`internalDate` for Gmail, `updated` for events, `modifiedTime` for Drive) to decide what changed since last sync.[^2_2][^2_5][^2_12][^2_3]
- Store a sync state (e.g., last sync time or per‑item version) in your own database.
- Be careful with deletions and conflict resolution: decide whether “latest wins,” or if local changes should override Google.

Do you plan to run this sync from a single personal machine (desktop script/cron) or as a multi‑user web app where different people connect their Google accounts?
<span style="display:none">[^2_15][^2_16][^2_17]</span>

<div align="center">⁂</div>

[^2_1]: https://developers.google.com/workspace/gmail/api/auth/scopes

[^2_2]: https://developers.google.com/workspace/calendar/api/auth

[^2_3]: https://blog.zephyrok.com/google-drive-api-with-python/

[^2_4]: https://davemateer.com/2022/04/28/google-drive-with-python

[^2_5]: https://www.merge.dev/blog/google-drive-api-python

[^2_6]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify

[^2_7]: https://stackoverflow.com/questions/19102557/google-oauth-scope-for-sending-mail

[^2_8]: https://googleapis.dev/dotnet/Google.Apis.Gmail.v1/latest/api/Google.Apis.Gmail.v1.GmailService.ScopeConstants.html

[^2_9]: https://developers.google.com/identity/protocols/oauth2/scopes

[^2_10]: https://help.okta.com/wf/en-us/content/topics/workflows/connector-reference/googlecalendar/overviews/scopes.htm

[^2_11]: https://forums.nylas.com/t/why-do-we-need-the-full-calendar-scope-to-create-events-for-gmail-calendar/38

[^2_12]: https://developers.google.com/workspace/gmail/api/quickstart/python

[^2_13]: https://developers.google.com/workspace/calendar/api/quickstart/python

[^2_14]: https://stackoverflow.com/questions/75330412/access-scope-for-shared-calendar-on-google-calendar-api

[^2_15]: https://gmailr.r-lib.org/reference/gm_scopes.html

[^2_16]: https://learn.emailengine.app/docs/accounts/gmail-api

[^2_17]: https://www.youtube.com/watch?v=6vKMvjcGDPs


---

# Would this allow me to forward emails unaltered? I’ve found this to be problematic in the past but it’s the only way to get reader to keep from mangling them.

Yes, you can effectively “forward” an email without mangling it by working with the raw RFC 822 message via the Gmail API, instead of reconstructing the body yourself.[^3_1][^3_2][^3_3]

## Two main options

- Auto‑forwarding via Gmail settings
    - You can enable account‑level auto‑forwarding or filter‑based forwarding through the Gmail API `users.settings.forwardingAddresses` and `updateAutoForwarding`.[^3_4][^3_5][^3_6]
    - This behaves like Gmail’s built‑in forwarding (the message that arrives should look exactly as Gmail forwards it in the UI).
- Manual forward while preserving content
    - Fetch the original message with `format='raw'`:
`msg = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()`.[^3_2][^3_1]
    - `msg['raw']` is the full RFC 2822 email, base64url encoded; if you decode it and then re‑encode and send it as a new message, you keep all MIME parts (HTML, text, attachments) intact.[^3_3][^3_1][^3_2]

Example pattern in Python (conceptual):

```python
import base64

orig = gmail.users().messages().get(
    userId="me", id=message_id, format="raw"
).execute()
raw = orig["raw"]  # base64url string from Gmail

# Option A: adjust headers minimally (e.g., change To:) by decoding.
mime_bytes = base64.urlsafe_b64decode(raw.encode("utf-8"))
# ...optionally tweak headers using the email library...
forward_raw = base64.urlsafe_b64encode(mime_bytes).decode("utf-8")

gmail.users().messages().send(
    userId="me",
    body={"raw": forward_raw}
).execute()
```

Because you’re sending a full RFC 822 message in `raw`, Gmail does not try to rebuild the structure, so HTML formatting, inline images, and attachments stay as‑is.[^3_7][^3_1][^3_2][^3_3]

## When things get “mangled”

- Problems usually appear when you extract just the text or HTML parts from `payload` and then build a new MIME message by hand; it’s easy to lose multipart boundaries, headers, or content‑transfer encodings.[^3_8][^3_9][^3_7][^3_3]
- Using `format='raw'` and treating the message as an opaque blob avoids this; alternatively, if you must modify it, use Python’s `email` package to preserve MIME structure carefully.[^3_10][^3_11][^3_3]

Are you trying to forward to another email inbox or into a different system (like a reader service / app)?
<span style="display:none">[^3_12][^3_13][^3_14][^3_15]</span>

<div align="center">⁂</div>

[^3_1]: https://googleapis.github.io/google-api-python-client/docs/dyn/gmail_v1.users.messages.html

[^3_2]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages

[^3_3]: https://mailtrap.io/blog/send-emails-with-gmail-api/

[^3_4]: https://developers.google.com/workspace/gmail/api/guides/forwarding_settings

[^3_5]: https://developers.google.com/workspace/gmail/api/guides

[^3_6]: https://support.google.com/mail/answer/10957?hl=en

[^3_7]: https://community.make.com/t/forwarding-gmails-while-maintainig-format/91665

[^3_8]: https://www.reddit.com/r/learnpython/comments/1jv8ktu/why_is_the_gmail_api_transforming_my_mail_parts/

[^3_9]: https://discuss.google.dev/t/maintaining-original-email-formatting-when-forwarding-gmail-messages-to-slack/172360

[^3_10]: https://community.latenode.com/t/automatically-forwarding-emails-with-gmail-api-and-custom-content/11482

[^3_11]: https://community.latenode.com/t/forwarding-emails-with-additional-content-via-gmail-api/8738

[^3_12]: https://stackoverflow.com/questions/77496677/python-forward-a-gmail-message-using-google-api

[^3_13]: https://stackoverflow.com/questions/38065356/error-sending-mail-with-google-api-raw-rfc822-payload-message-string-or-upl

[^3_14]: https://stackoverflow.com/questions/30762369/gmail-api-playground-send-method-converted-mime-raw-header-not-populating-emai

[^3_15]: https://stackoverflow.com/a/44848269


---

# Readwise service so I can access via their reader app.

For Readwise Reader, the easiest and most robust approach is to forward emails directly to your custom Reader email address, using Gmail’s auto‑forwarding or a rule/label, not by rebuilding the email body yourself.[^4_1][^4_2][^4_3][^4_4][^4_5]

## How Reader wants emails

- Reader gives you one or more unique email addresses (e.g. `something@feed.readwise.io` or `something@library.readwise.io`) that you can send or forward mail to; anything mailed there shows up in your Feed/Library.[^4_2][^4_3][^4_5][^4_6][^4_1]
- You can find these addresses in Reader under import/integrations settings; they’re meant to receive normal, unmodified emails, newsletters, etc.[^4_3][^4_5][^4_1][^4_2]


## Best way to avoid mangling

If your past problems were Reader mangling formatting when it parses content, you want the message to arrive exactly as Gmail received it.

You have two strong options:

1. **Use Gmail’s built‑in auto‑forwarding / filters (recommended if possible)**
    - In Gmail settings → “Forwarding and POP/IMAP”, add your Reader email as a forwarding address, then complete the confirmation flow (Reader auto‑clicks the link or sends you the confirmation code).[^4_4][^4_7][^4_1][^4_2][^4_3]
    - Use filters to forward only newsletters or specific senders to Reader; Gmail forwards the original email, keeping all headers and MIME parts intact.[^4_1][^4_2][^4_4]
2. **Use the Gmail API with `format='raw'` and send to Reader**
    - Fetch the message with `format='raw'` to get the full RFC 822 content as base64url; this keeps HTML, text, and attachments as‑is.[^4_8][^4_9][^4_10]
    - Decode only if you need to adjust headers, then re‑encode and send to the Reader address as a new Gmail message; from Reader’s perspective it receives a normal, complete email.

Conceptual Python snippet:

```python
import base64

orig = gmail.users().messages().get(
    userId="me", id=message_id, format="raw"
).execute()

raw = orig["raw"]  # base64url RFC 822 from Gmail

# Optionally tweak headers using `email` library here; otherwise pass through.
forward_raw = raw  # unchanged

gmail.users().messages().send(
    userId="me",
    body={"raw": forward_raw}  # To: header inside raw must be your Reader address
).execute()
```

The key is to work with the **raw** message blob so you’re not reassembling parts; that keeps Reader from seeing something partially reconstructed.[^4_9][^4_10][^4_11][^4_12][^4_8]

## Bonus: Use the Reader API for downstream sync

Once emails land in Reader, you can use the Reader API to pull documents, locations (new, later, archive, feed), and metadata into your own system alongside Gmail/Calendar/Drive.[^4_13][^4_14]


| Piece | How it flows into Reader |
| :-- | :-- |
| Gmail newsletters | Forwarded to your Reader email via Gmail or API.[^4_1][^4_2][^4_3][^4_4] |
| Reader documents | Queried via Reader API `/api/v3/list/` and other endpoints.[^4_13][^4_14] |

Do you want to move *all* mail that matches a filter into Reader automatically, or selectively forward only specific messages on demand from your Python script?
<span style="display:none">[^4_15][^4_16][^4_17][^4_18][^4_19][^4_20]</span>

<div align="center">⁂</div>

[^4_1]: https://docs.readwise.io/reader/docs/faqs/email-newsletters

[^4_2]: https://blog.readwise.io/p/f8c0f71c-fe5f-4025-af57-f9f65c53fed7/

[^4_3]: https://docs.readwise.io/reader/llms.txt

[^4_4]: https://productivitystack.substack.com/p/how-to-get-newsletters-out-of-your

[^4_5]: https://www.reddit.com/r/readwise/comments/12axpjm/emailing_items_to_reader_account/

[^4_6]: https://www.reddit.com/r/readwise/comments/1gwiv02/best_way_to_get_emails_into_reader/

[^4_7]: https://dominiknitsch.substack.com/p/ig28-the-best-way-to-read-newsletters

[^4_8]: https://googleapis.github.io/google-api-python-client/docs/dyn/gmail_v1.users.messages.html

[^4_9]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages

[^4_10]: https://mailtrap.io/blog/send-emails-with-gmail-api/

[^4_11]: https://www.reddit.com/r/learnpython/comments/1jv8ktu/why_is_the_gmail_api_transforming_my_mail_parts/

[^4_12]: https://community.make.com/t/forwarding-gmails-while-maintainig-format/91665

[^4_13]: https://readwise.io/api_deets

[^4_14]: https://readwise.io/reader_api

[^4_15]: https://www.reddit.com/r/readwise/comments/1q5l6se/forwarding_from_gmail_or_subscribe_with_reader/

[^4_16]: https://docs.readwise.io/readwise/docs/faqs

[^4_17]: https://www.youtube.com/watch?v=YEUdL8rhZsY

[^4_18]: https://www.reddit.com/r/readwise/comments/1nztuui/readwise_api_documentation/

[^4_19]: https://docs.readwise.io/reader/docs/migrating-content

[^4_20]: https://docs.readwise.io/reader/docs/faqs/importing-content


---

# Provide full instructions on the implementation of a fully functional tool to access my gmail and google calendar using local python tools as discussed in this thread.

Here's the complete implementation guide — it covers everything from Google Cloud setup through to working, production-ready Python code.

The report is organized into 9 parts:

1. **Google Cloud Setup** — creating a project, enabling the Gmail and Calendar APIs, configuring the OAuth consent screen, and downloading `credentials.json`[^5_1][^5_2][^5_3]
2. **Python environment** — the three packages to install and the recommended project layout[^5_3][^5_4]
3. **Shared auth module** (`google_client.py`) — the token-caching OAuth flow that opens a browser once and silently refreshes ever after[^5_5][^5_6][^5_7]
4. **Gmail tool** (`gmail_tool.py`) — list/search, read metadata, read full body, read raw RFC 2822, send new messages, mark read/unread, archive, trash, and label[^5_8][^5_9][^5_10][^5_11][^5_12]
5. **Calendar tool** (`calendar_tool.py`) — list upcoming events, list by date range, create timed and all-day events, update, and delete[^5_13][^5_14][^5_15][^5_16][^5_1]
6. **Readwise Reader forwarding** (`readwise_sync.py`) — queries Gmail for unread newsletters and forwards them raw to your Reader inbound email address, body completely untouched[^5_17][^5_18][^5_19][^5_20][^5_21]
7. **First-run checklist** — the exact sequence of steps to go from nothing to working
8. **Scope reference table** — all scopes with their access levels[^5_11][^5_22][^5_23]
9. **Token management \& troubleshooting** — how to handle the 7-day testing expiry, common errors and their fixes, and an exponential-backoff retry helper[^5_24][^5_25][^5_26]

The key forward-without-mangling technique is in `forward_message_raw`: fetch `format='raw'`, parse with Python's `email` library (which never re-encodes), swap only the routing headers (`To`, `Cc`, old `DKIM-Signature`), and send back as base64url. The HTML body and all MIME parts never get touched.[^5_18][^5_19][^5_20][^5_27]
<span style="display:none">[^5_28][^5_29][^5_30][^5_31][^5_32][^5_33][^5_34][^5_35][^5_36][^5_37][^5_38][^5_39][^5_40][^5_41][^5_42][^5_43][^5_44][^5_45][^5_46][^5_47][^5_48][^5_49][^5_50][^5_51][^5_52][^5_53][^5_54][^5_55][^5_56][^5_57][^5_58][^5_59][^5_60][^5_61][^5_62][^5_63][^5_64][^5_65][^5_66][^5_67][^5_68][^5_69][^5_70][^5_71][^5_72][^5_73][^5_74][^5_75][^5_76][^5_77][^5_78][^5_79][^5_80][^5_81][^5_82][^5_83][^5_84][^5_85][^5_86][^5_87][^5_88][^5_89][^5_90][^5_91][^5_92][^5_93][^5_94][^5_95][^5_96][^5_97]</span>

<div align="center">⁂</div>

[^5_1]: https://developers.google.com/people/quickstart/python

[^5_2]: https://developers.google.com/workspace/calendar/api/quickstart/python

[^5_3]: https://developers.google.com/workspace/gmail/api/quickstart/python

[^5_4]: https://developers.google.com/workspace/guides/configure-oauth-consent

[^5_5]: https://docs.intellibuddies.com/docs/pd/connecting-to-google/

[^5_6]: https://developers.google.com/identity/protocols/oauth2

[^5_7]: https://googleapis.github.io/google-api-python-client/docs/oauth-installed.html

[^5_8]: https://pypi.org/project/google-api-python-client/

[^5_9]: https://googleapis.github.io/google-api-python-client/docs/oauth.html

[^5_10]: https://thepythoncode.com/article/use-gmail-api-in-python

[^5_11]: https://developers.google.com/workspace/gmail/api/guides/list-messages

[^5_12]: https://developers.google.com/workspace/gmail/api/guides/sending

[^5_13]: https://developers.google.com/workspace/gmail/api/auth/scopes

[^5_14]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify

[^5_15]: https://www.youtube.com/watch?v=_uHd0ypR5OI

[^5_16]: https://developers.google.com/workspace/calendar/api/v3/reference/events/delete

[^5_17]: https://github.com/balirampansare/google-calendar-api-python

[^5_18]: https://googleapis.github.io/google-api-python-client/docs/dyn/calendar_v3.events.html

[^5_19]: https://endgrate.com/blog/how-to-get-calendar-events-with-the-google-calendar-api-in-python

[^5_20]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages

[^5_21]: https://docs.python.org/3/library/email.message.html

[^5_22]: https://www.reddit.com/r/learnpython/comments/1jv8ktu/why_is_the_gmail_api_transforming_my_mail_parts/

[^5_23]: https://community.make.com/t/forwarding-gmails-while-maintainig-format/91665

[^5_24]: https://googleapis.github.io/google-api-python-client/docs/dyn/gmail_v1.users.messages.html

[^5_25]: https://docs.readwise.io/reader/docs/faqs/email-newsletters

[^5_26]: https://blog.readwise.io/p/f8c0f71c-fe5f-4025-af57-f9f65c53fed7/

[^5_27]: https://docs.readwise.io/reader/llms.txt

[^5_28]: https://stackoverflow.com/questions/19102557/google-oauth-scope-for-sending-mail

[^5_29]: https://developers.google.com/identity/protocols/oauth2/scopes

[^5_30]: https://developers.google.com/workspace/calendar/api/auth

[^5_31]: https://blog.zephyrok.com/google-drive-api-with-python/

[^5_32]: https://davemateer.com/2022/04/28/google-drive-with-python

[^5_33]: https://www.merge.dev/blog/google-drive-api-python

[^5_34]: https://community.latenode.com/t/gmail-api-refresh-token-keeps-expiring-how-to-prevent-automatic-expiration/35297

[^5_35]: https://github.com/googlemaps/google-maps-services-python/issues/109

[^5_36]: https://docs.cloud.google.com/python/docs/reference/storage/latest/retry_timeout

[^5_37]: https://brightdata.com/blog/web-data/retry-failed-requests-python

[^5_38]: https://googleapis.dev/python/google-api-core/latest/retry.html

[^5_39]: https://stackoverflow.com/questions/65816603/how-to-generate-client-secret-json-for-google-api-with-offline-access

[^5_40]: https://developers.google.com/workspace/guides/create-credentials

[^5_41]: https://googleapis.github.io/google-api-python-client/docs/start.html

[^5_42]: https://github.com/googleapis/google-api-python-client/blob/main/docs/client-secrets.md?plain=1

[^5_43]: https://stackoverflow.com/questions/77496677/python-forward-a-gmail-message-using-google-api

[^5_44]: https://docs.cloud.google.com/docs/authentication/client-libraries

[^5_45]: https://github.com/googleapis/google-auth-library-python/blob/main/google/oauth2/credentials.py

[^5_46]: https://www.youtube.com/watch?v=ufBoCdj0eYM

[^5_47]: https://formacionpoliticaisc.buenosaires.gob.ar/breaking-review/python-google-api-client-quick-start-guide-1767647990

[^5_48]: https://developers.google.com/identity/protocols/oauth2/web-server

[^5_49]: https://stackoverflow.com/questions/78733253/update-all-future-events-using-google-calendar-api

[^5_50]: https://stackoverflow.com/questions/44821814/trying-to-send-email-with-gmail-api-receive-raw-rfc822-payload-message-string

[^5_51]: https://support.google.com/googleapi/answer/6158849?hl=en

[^5_52]: https://mailtrap.io/blog/python-send-email-gmail/

[^5_53]: https://www.youtube.com/watch?v=1JkKtGFnua8

[^5_54]: https://github.com/google/adk-python/discussions/3512

[^5_55]: https://www.youtube.com/watch?v=29eJb5IIBDs

[^5_56]: https://community.latenode.com/t/automatically-forwarding-emails-with-gmail-api-and-custom-content/11482

[^5_57]: https://www.oauth.com/oauth2-servers/making-authenticated-requests/refreshing-an-access-token/

[^5_58]: https://www.youtube.com/watch?v=p7cn1n1kx3I

[^5_59]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format

[^5_60]: https://stackoverflow.com/questions/73584575/gmail-api-with-python

[^5_61]: https://behainguyen.wordpress.com/2022/05/09/gmail-api-quick-start-with-python-and-nodejs/

[^5_62]: https://github.com/googleworkspace/python-samples/blob/main/gmail/quickstart/quickstart.py

[^5_63]: https://www.reddit.com/r/pythontips/comments/1pbdoch/python_to_read_mail_from_gmail_using_google_api/

[^5_64]: https://ftp.broadwayinfosys.com/blog/python-google-api-simplified-guide-and-client-library-1767647990

[^5_65]: https://www.youtube.com/watch?v=7X3fBlMw_1k

[^5_66]: https://stackoverflow.com/questions/31437541/using-google-calendar-api-with-an-api-key-python

[^5_67]: https://github.com/googleapis/google-api-python-client

[^5_68]: https://www.pythonanywhere.com/forums/topic/28606/

[^5_69]: https://github.com/alexandrumd/google-calendar-quickstart

[^5_70]: https://gmailr.r-lib.org/reference/gm_scopes.html

[^5_71]: https://googleapis.dev/dotnet/Google.Apis.Gmail.v1/latest/api/Google.Apis.Gmail.v1.GmailService.ScopeConstants.html

[^5_72]: https://help.okta.com/wf/en-us/content/topics/workflows/connector-reference/googlecalendar/overviews/scopes.htm

[^5_73]: https://learn.emailengine.app/docs/accounts/gmail-api

[^5_74]: https://stackoverflow.com/questions/75330412/access-scope-for-shared-calendar-on-google-calendar-api

[^5_75]: https://www.youtube.com/watch?v=6vKMvjcGDPs

[^5_76]: https://forums.nylas.com/t/why-do-we-need-the-full-calendar-scope-to-create-events-for-gmail-calendar/38

[^5_77]: https://developers.google.com/workspace/gmail/api/guides/forwarding_settings

[^5_78]: https://developers.google.com/workspace/gmail/api/guides

[^5_79]: https://stackoverflow.com/questions/38065356/error-sending-mail-with-google-api-raw-rfc822-payload-message-string-or-upl

[^5_80]: https://stackoverflow.com/questions/30762369/gmail-api-playground-send-method-converted-mime-raw-header-not-populating-emai

[^5_81]: https://support.google.com/mail/answer/10957?hl=en

[^5_82]: https://stackoverflow.com/a/44848269

[^5_83]: https://discuss.google.dev/t/maintaining-original-email-formatting-when-forwarding-gmail-messages-to-slack/172360

[^5_84]: https://community.latenode.com/t/forwarding-emails-with-additional-content-via-gmail-api/8738

[^5_85]: https://mailtrap.io/blog/send-emails-with-gmail-api/

[^5_86]: https://www.reddit.com/r/readwise/comments/1q5l6se/forwarding_from_gmail_or_subscribe_with_reader/

[^5_87]: https://productivitystack.substack.com/p/how-to-get-newsletters-out-of-your

[^5_88]: https://docs.readwise.io/readwise/docs/faqs

[^5_89]: https://www.reddit.com/r/readwise/comments/12axpjm/emailing_items_to_reader_account/

[^5_90]: https://readwise.io/api_deets

[^5_91]: https://www.youtube.com/watch?v=YEUdL8rhZsY

[^5_92]: https://www.reddit.com/r/readwise/comments/1gwiv02/best_way_to_get_emails_into_reader/

[^5_93]: https://readwise.io/reader_api

[^5_94]: https://www.reddit.com/r/readwise/comments/1nztuui/readwise_api_documentation/

[^5_95]: https://dominiknitsch.substack.com/p/ig28-the-best-way-to-read-newsletters

[^5_96]: https://docs.readwise.io/reader/docs/migrating-content

[^5_97]: https://docs.readwise.io/reader/docs/faqs/importing-content

