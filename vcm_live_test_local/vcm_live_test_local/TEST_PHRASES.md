# Phrases to read - VCM One-Shot

Say the wake word first (**Nova** or **Piattos**), then one phrase from the list below. The app
records a single 5 s window and makes exactly one decision, so re-arm before each phrase.

31 phrases across the 19 command classes:

| Intent | Say this |
| --- | --- |
| PLAY_MUSIC | play some music |
| WEATHER | what's the weather today |
| TIME | what time is it |
| LIGHT_ON | turn on the lights |
| LIGHT_OFF | turn off the lights |
| PAUSE | pause the music |
| STOP | stop |
| NEXT | next song |
| VOLUME_UP | turn the volume up |
| VOLUME_DOWN | turn the volume down |
| CALL | call mom |
| MESSAGE | send a message to john |
| LIST_REMINDERS | list my reminders |
| TIMER | set a timer for 10 seconds / 30 seconds / 1 minute |
| ALARM | set an alarm for 6 am / 8 am / 9 pm |
| TEMPERATURE | set the temperature to 18 / 22 / 26 degrees |
| BRIGHTNESS | set brightness to 20 / 60 / 100 percent |
| COLOR | make the lights red / blue / green |
| CREATE_REMINDER | remind me to drink water / study / exercise |

The same list appears inside the app: open **Phrases to read** under the results panel, and it is
served from `gate1_web/data/test_phrases.json`.

For a rejection check (the app should answer *no intent* or low confidence), say the wake word
followed by something outside the list, for example "what is the capital of France".
