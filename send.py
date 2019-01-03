from limesurveyrc2api.limesurvey import LimeSurvey
from limesurveyrc2api.exceptions import LimeSurveyError
from getpass import getpass
from time import sleep
from argparse import ArgumentParser
import sys
from datetime import datetime as dt
from collections import OrderedDict

import json

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(levelname)s] %(message)s')

handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
handler.setLevel(logging.DEBUG)

logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

profiles = {}
default = {}
settings = {}

def days_between(d1, d2, date_format):
    d1 = dt.strptime(d1, date_format)
    d2 = dt.strptime(d2, date_format)
    diff = abs((d2 - d1).days)
    #logger.debug("Calculated days between for {} and {} as {}".format(
    #    d1, d2, diff
    #))
    return diff

def ok_to_send(question, default="no"):

    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    yes = False

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("[ERROR] Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def get_uninvited(api, survey_id):
    participants = {p['tid']:p for p in api.token.list_participants(
        survey_id,
        limit=100000,
        ignore_token_used=True,
        attributes=['emailstatus','sent'],
        conditions={'emailstatus': 'OK', 'sent':'N'}
    ) if p['emailstatus']=='OK' and p['sent']=='N'}    
    
    return list(participants.keys()), participants

def get_unreminded(api, survey_id, min_days_between, max_reminders):
    global settings
    participants = {}

    for rem in range(max_reminders):
        try:
            print(rem)
            participants.update({p['tid']:p for p in api.token.list_participants(
                survey_id,
                limit=1000000,
                ignore_token_used=True,
                attributes=['emailstatus','sent', 'remindercount', 'usesleft', 'remindersent'],
                conditions={
                    'emailstatus': 'OK',
                    'remindercount':rem,
                    #'min_days_between': min_days_between,
                    'usesleft': 1
                })
                if(
                    p['emailstatus']=='OK' and
                    int(p['usesleft'])>0 and
                    int(p['remindercount'])<max_reminders and

                    # weirdly, the field 'remindersent' can either contain Y/N or the 
                    # date of the last reminder sent...
                    (p['remindersent']=='N' or p['remindersent']=='Y' or
                        days_between(
                            p['remindersent'],
                            dt.now().strftime(settings['date_format']),
                            settings['date_format']
                        )>=min_days_between)
            )})
            print(len(participants))

        except LimeSurveyError as e:
            if not e.message == "Error during query | list_participants | No survey participants found.":
                logger.error(e.message)
                sys.exit(1)

    logger.info(len(participants.keys()))

    return list(participants.keys()), participants


def send_mails(api, survey_id, get_participants_func, get_participants_args,
               send_mails_func, send_mails_args, batch_size,
               wait, max_batches):
    try:
        p_ids, participants = get_participants_func(**get_participants_args)
    except LimeSurveyError:
        logger.error("Could not connect. Check url, username and password.")
        sys.exit(1) 

    sending_done = False
    all_sent = []
    num_batches = min(max_batches, int(round(len(p_ids)/batch_size)))
    current_batch = 0

    ok = ok_to_send("[?] {} e-mails will be sent. Continue?".format(
        min(batch_size*max_batches,len(p_ids))
    ))

    while ok and not sending_done:
        current_batch += 1
        batch_status = "batch {}/{}: ".format(current_batch, num_batches)
        sent = []
        try:
            send_args = {
                **{
                    'survey_id': survey_id,
                    'token_ids': p_ids[:min(len(p_ids), batch_size)]
                },
                **send_mails_args
            }

            logger.info("Sending {} e-mails to participants: {}".format(
            	len(send_args['token_ids']),
            	",".join(send_args['token_ids'])
            ))

            # send mails and strip results of 'status' field to get number of sent mails
            try:
                sent = [v for k,v in send_mails_func(**send_args).items() if not k=="status"]
            except LimeSurveyError as e:
                logger.error("Could not send any e-mails.")
                logger.error(e.message)
                sys.exit(1) 
            
            all_sent.extend(sent)

        except LimeSurveyError as e:
            pass

        # finish
        p_ids, participants = get_participants_func(**get_participants_args)
        
        if current_batch == max_batches:
            logger.info("{} Hit maximum batch number.".format(batch_status, len(p_ids)))
            sending_done = True            

        if len(p_ids)==0 or current_batch == max_batches:
            logger.info("{} Sending done. Sent {} e-mails in total.".format(batch_status, len(all_sent)))
            sending_done = True

        elif len(sent)==0 and len(p_ids)>0:
            logger.warn("{} Could not send e-mails to all participants, {} left unsent.".format(batch_status, min(batch_size*max_batches,len(p_ids))))
            sending_done = True

        else:
            if not sending_done:            
                logger.info("{} Sent e-mails to {} participants. Waiting {} seconds for next batch...".format(
                    batch_status, len(sent), wait
                ))
                sleep(wait)
            
    return all_sent

def connect(url, survey_id):
    #print("Please enter your username")
    username=getpass(prompt="[?] Please enter your username:")
    #print("Please enter your password")
    password=getpass(prompt="[?] Please enter your password:")

    try:
        api = LimeSurvey(url=url, username=username)
        api.open(password=password)        
    except Exception:
        logger.error("Could not connect. Check url, username and password.")
        sys.exit(1)        


    surveys = {int(s['sid']): s for s in api.survey.list_surveys()}
    if len(surveys)>0:
        logger.info("Connected to server.")
        if survey_id == -1:
            return surveys
        else:        
            if survey_id in surveys.keys():
                title = surveys[survey_id]['surveyls_title']
                active = "active" if surveys[survey_id]['active'] == 'Y' else "inactive"
                logger.info("Selected survey: {}. Survey status: {}".format(title, active))
                return api
            else:
                logger.error("Selected survey not found")
                sys.exit(1)
    else:
        logger.error("Could not find any surveys")
        sys.exit(1)
        


def disconnect(api):
    api.close()
    logger.info("Disconnected from server.")
    sys.exit(0)

def send_invitations(url, survey_id, batch_size, wait, max_batches):
    api = connect(url, survey_id)
    results = send_mails(
        api, survey_id,
        get_uninvited, {'api': api, 'survey_id': survey_id},
        api.token.invite_participants, {'uninvited_only': True},
        batch_size,
        wait,
        max_batches
    )
    disconnect(api)

    return results

# based on limesurvey's PHP API
# https://api.limesurvey.org/classes/remotecontrol_handle.html#method_invite_participants
# remind_participants(string $sSessionKey, integer $iSurveyID,
#                     integer $iMinDaysBetween = null,
#                     integer $iMaxReminders = null,
#                     array $aTokenIds = false) : array
def remind_participants(api, survey_id, token_ids, min_days_between, max_reminders):
    """
    Send invitation emails for the specified survey participants.
    Parameters
    :param survey_id: ID of survey to invite participants from.
    :type survey_id: Integer
    :param token_ids: List of token IDs for participants to invite.
    :type token_ids: List[Integer]
    :param uninvited_only: If True, only send emails for participants that
      have not been invited. If False, send an invite even if already sent.
    :type uninvited_only: Bool
    """
    method = "remind_participants"
    params = OrderedDict([
        ("sSessionKey", api.session_key),
        ("iSurveyID", survey_id),
        ("iMinDaysBetween", min_days_between),
        ("iMaxReminders", max_reminders),
        ("aTokenIDs", token_ids)
    ])
    response = api.query(method=method, params=params)
    response_type = type(response)

    if response_type is dict and "status" in response:
        status = response["status"]
        error_messages = [
            "Invalid session key",
            "Error: Invalid survey ID",
            "Error: No token table",
            "Error: No candidate tokens",
            "No permission",
        ]
        for message in error_messages:
            if status == message:
                raise LimeSurveyError(method, status)
    else:
        assert response_type is dict

    return response

def send_reminders(url, survey_id, batch_size, wait, max_batches, min_days_between, max_reminders):
    api = connect(url, survey_id)
    results = send_mails(
        api, survey_id,
        get_unreminded, {
            'api': api,
            'survey_id': survey_id,
            'min_days_between': min_days_between,
            'max_reminders': max_reminders
        },
        remind_participants, {
            'api': api,
            'min_days_between': min_days_between,
            'max_reminders': max_reminders
        },
        batch_size,
        wait,
        max_batches
    )
    disconnect(api)

    return results


def main():
    global settings

    try:
        with open("config.json") as default_json:
            profiles = json.load(default_json)
        default = profiles['default']
    except Exception:
        logger.error("Could not load default profile.")
        exit(0)

    parser = ArgumentParser(description='Batch-send invitations and reminders for limesurvey surveys.')
    parser.add_argument('action', type=str, help='invite / remind / list')
    parser.add_argument('-p', '--profile', type=str, help='path to a json configuration file, use arguments provided there, except arguments provided in CL deviate from default values')
    parser.add_argument('-s', '--survey-id', type=int, help='ID of the targeted survey in limesurvey', default=default['survey_id'])
    parser.add_argument('-u', '--url', type=str, help='url of limesurvey api', default=default['url'])
    parser.add_argument('-b', '--batch-size', type=int, help='how many emails to send in one batch', default=default['batch_size'])
    parser.add_argument('-w', '--wait', type=int, help='how long to wait between sending each batch, in seconds', default=default['wait'])
    parser.add_argument('-m', '--max-batches', type=int, help='how many batches to send max.', default=default['max_batches'])
    parser.add_argument('-d', '--min-days-between', type=int, help='how many days before a second reminder can be sent, default 14', default=default['min_days_between'])
    parser.add_argument('-r', '--max-reminders', type=int, help='how may reminders are max. allowed to be sent to each contact, default 1', default=default['max_reminders'])
    parser.add_argument('-f', '--date-format', type=str, help='date format used in limesurvey, default %d.%m.%Y', default=default['date_format'])

    args = parser.parse_args()

    if args.profile:
        try:        
            settings = profiles[args.profile]
            for k in settings.keys():
                if getattr(args,k) != default[k]:
                    settings[k] = getattr(args,k)          
        except Exception as e:
            logger.error(str(e))
            logger.error("Could not load profile.")
            exit(0)

    else:
        settings = dict(
            url=args.url,
            survey_id=args.survey_id,
            batch_size=args.batch_size,
            wait=args.wait,
            max_batches=args.max_batches,
            min_days_between=args.min_days_between,
            max_reminders=args.max_reminders,
            date_format=args.date_format
        )

    logger.info(args.action + " with settings:")
    for s in ["{}={}".format(k,v) for k,v in settings.items()]:
        logger.info(s)
    
    if args.action == "invite":
        if settings['survey_id']==-1:
            logger.error("No survey selected.")
        else:
            send_invitations(
                url=settings['url'],
                survey_id=settings['survey_id'],
                batch_size=settings['batch_size'],
                wait=settings['wait'],
                max_batches=settings['max_batches']
            )

    elif args.action == "remind":
        if settings['survey_id']==-1:
            logger.error("No survey selected.")
        else:        
            send_reminders(
                url=settings['url'],
                survey_id=settings['survey_id'],
                batch_size=settings['batch_size'],
                wait=settings['wait'],
                max_batches=settings['max_batches'],
                min_days_between=settings['min_days_between'],
                max_reminders=settings['max_reminders']            
            )

    elif args.action == "list":
        surveys = connect(settings['url'], survey_id=-1)
        for sid, s in surveys.items():
            title = s['surveyls_title']
            active = "active" if s['active'] == 'Y' else "inactive"            
            logger.info("{} - {} ({})".format(sid, title, active))


if __name__ == "__main__":
    main()    