# limesurvey-sender
A CLI for batch-sending invitations and reminders for limesurveys. Used to avoid SMTP-server overload and time-consuming manual usage of limesurvey webUI. Includes limesurveyrc2api from https://github.com/lindsay-stevens/limesurveyrc2api (+own implementations of missing methods).


```
Usage:
  send.py list --url <url>
  send.py invite --url <url> --survey-id <survey-id> [options]
  send.py remind --url <url> --survey-id <survey-id> [options]

Options:
  -u URL --url URL                  url of limesurvey api
  -s ID --survey-id ID              ID of the targeted survey in limesurvey [default:-1]
  -b SIZE --batch-size SIZE         how many emails to send in one batch [default:100]
  -w SECS --wait SECS               how long to wait between sending each batch, in seconds [default:30]
  -m MAX --max-batches MAX          how many batches to send max [default:1000000]
  -d DAYS --min-days-between DAYS   how many days before a second reminder can be sent [default:14]
  -r MAX --max-reminders  MAX       how may reminders are max. allowed to be sent to each contact [default:1]
  -f FORMAT --date-format FORMAT    date format used in limesurvey [default:"%d.%m.%Y"]
