# LLM Report Bot

Claude Code와 Codex가 이 PC에 남긴 로컬 JSONL 로그를 읽어 Discord로 사용량을 알려주는 Windows용 개인 봇입니다. `/usage`로 사용량을 확인하고, `/work`로 로컬 LLM 작업 상태를 확인할 수 있습니다. `/help`는 사용 가능한 명령어를 표시하며, `/status`와 `/settings`는 안전한 운영 정보를 개인 응답으로 보여줍니다.


## 만든 이유와 개발 방식

Claude Code와 Codex의 토큰 사용량을 매번 확인하고 계산하는 번거로움을 줄이기 위해 만든 개인 도구입니다.
필요한 기능과 동작을 정리하고, 코드 구현에는 AI 개발 도구의 도움을 받았습니다.

## 데이터 처리 범위

- Claude Code와 Codex의 로컬 JSONL 로그를 직접 읽어 집계합니다. 별도 토큰 모니터 앱이나 데이터베이스를 요구하지 않습니다.
- 실제 실행은 Windows를 대상으로 하며 Python 3.10 이상이 필요합니다.
- 작업 요약 전송은 기본적으로 꺼져 있습니다. `WORK_INCLUDE_SUMMARY=1`로 켜면 최종 응답 내용의 일부가 Discord에 전송될 수 있습니다.
- `DISCORD_ALLOWED_USER_IDS`는 필수입니다. 비어 있거나 ID 형식이 잘못되면 봇을 시작하지 않습니다. 채널 허용 목록은 추가 제한으로 사용할 수 있습니다.
- `/usage`, `/work`, `/help`, `/status`, `/settings` 응답은 요청한 사용자에게만 보입니다. 자동 웹훅 알림은 설정한 채널에 전송됩니다.
- Claude 사용률과 로그 유휴 시간에 따른 작업 완료 여부는 추정치입니다. 작업 토큰 값은 로그에서 읽은 누적값이며 개별 작업의 정확한 토큰 사용량을 뜻하지 않습니다.
- 복구 큐는 기본 비활성화되어 있으며, 활성화하면 사용자가 로컬에서 등록한 명령을 실행합니다.

## 주요 파일

| 파일 | 용도 |
| --- | --- |
| `LLM_report_bot.bat` | 더블클릭으로 트레이 관리자와 Discord 봇을 바로 시작합니다. |
| `run_llm_report.bat` | Discord 웹훅으로 사용량 리포트를 1회 전송합니다. |
| `run_llm_report_tray_debug.bat` | 트레이 관리자를 콘솔에서 디버그 실행합니다. |
| `start_llm_report_tray_hidden.vbs` | Windows 시작프로그램에서 콘솔창 없이 트레이 관리자를 실행합니다. |
| `tail_llm_report_logs.bat` | 최근 봇 로그를 계속 보여줍니다. |
| `tail_llm_report_logs.ps1` | UTF-8과 중요도 색상을 적용하는 실시간 로그 뷰어입니다. |
| `llm_report.py` | 1회성 사용량 리포트 CLI입니다. |
| `llm_report_bot.py` | `/usage`, `/work`, `/help`, `/status`, `/settings`, 자동 경보를 처리하는 Discord 봇입니다. |
| `llm_report_core.py` | Claude/Codex 로그 집계와 리포트 포맷을 담당합니다. |
| `llm_report_tray.py` | 트레이 아이콘, 봇 시작/중지/재시작, 시작프로그램 토글을 담당합니다. |

## 설치

```bat
cd /d path\to\LLM_report_bot
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Discord 봇 생성·초대

사용자가 자기 PC에서 자기 Discord 봇 계정과 설정으로 실행하는 방식입니다. 각 사용자는 자기 봇을 만들고 자기 서버로 초대합니다.

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 애플리케이션을 만들고 Bot 페이지에서 봇 토큰을 준비합니다. 토큰은 자기 PC의 `.env`에만 저장합니다.
2. General Information의 Application ID를 확인합니다. Application ID와 봇 토큰은 서로 다른 값입니다.
3. Installation에서 Guild Install을 사용하고, OAuth2 URL Generator에서 `bot`, `applications.commands`를 선택합니다. 채널 보기·메시지 보내기·링크 임베드 권한만 요청하며 관리자 권한은 필요하지 않습니다. 메시지 본문 접근용 Message Content Intent도 필요하지 않습니다.
4. 생성한 링크로 봇을 자기 서버에 추가합니다. 아래 형식에서 `YOUR_APPLICATION_ID`를 자기 앱 ID로 바꿔 사용해도 됩니다.

```text
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&scope=bot%20applications.commands&permissions=19456&integration_type=0
```

5. Discord의 개발자 모드를 켜고 자기 사용자 ID와 명령을 사용할 채널 ID를 복사해 `.env`의 허용 목록에 설정합니다.
6. 자동 알림이 필요하면 알림을 받을 채널의 웹훅을 만들고 `DISCORD_USAGE_WEBHOOK_URL`에 설정합니다. 작업 알림을 별도 채널로 받으려면 `DISCORD_WORK_WEBHOOK_URL`도 설정합니다.

OAuth2 설치 절차는 [Discord 공식 문서](https://docs.discord.com/developers/topics/oauth2)를 참고하세요.

## 다른 서버·사용자의 데이터와의 관계

- 실행 중인 PC의 로컬 로그만 집계합니다. 다른 사람이 이 저장소를 받아 자기 PC에서 자기 봇으로 실행하면 그 사람 PC의 로그를 처리합니다.
- 명령 응답은 허용 목록에 있는 요청자에게만 보입니다. 자동 알림은 `.env`에 설정한 웹훅 채널에 보내며, 봇을 초대한 서버의 모든 채널로 자동 전송하지 않습니다.
- 같은 봇 계정은 연결된 PC의 로그를 처리합니다. 다른 사람이 자기 정보를 확인하려면 자기 봇 토큰과 자기 PC의 실행 환경을 사용해야 합니다.
- 봇 초대 링크는 서버 설치용입니다. 알림을 받을 채널은 별도의 웹훅 설정으로 정합니다. [Discord 웹훅 문서](https://docs.discord.com/developers/resources/webhook)
- 공개 저장소에는 봇 토큰·실제 웹훅·개인 로그가 포함되지 않습니다.

## .env 설정

```bat
copy .env.example .env
notepad .env
```

| 변수 | 설명 |
| --- | --- |
| `DISCORD_USAGE_WEBHOOK_URL` | 1회 리포트와 자동 경보를 보낼 Discord 웹훅 URL입니다. |
| `DISCORD_BOT_TOKEN` | `/usage`, `/work`, `/help`, `/status`, `/settings` 명령을 처리할 Discord 봇 토큰입니다. |
| `DISCORD_ALLOWED_USER_IDS` | 필수 사용자 ID 목록입니다. 쉼표로 구분하며, 비우면 봇이 시작되지 않습니다. |
| `DISCORD_ALLOWED_CHANNEL_IDS` | 추가로 제한할 채널 ID 목록입니다. 비우면 허용 사용자에 한해 모든 채널에서 명령을 쓸 수 있습니다. |
| `DISCORD_BOT_NAME` | 봇 상태 메시지와 트레이 표시에 쓰는 이름입니다. 기본값은 `Your_LLM_Bot`입니다. |
| `DISCORD_WORK_WEBHOOK_URL` | 작업 완료/실패 알림 전용 웹훅입니다. 비우면 사용량 웹훅을 사용합니다. |
| `CLAUDE_PLAN` | Claude 5시간 잔여량 추정 기준입니다. 예: `free`, `pro`, `max_5x`, `max_20x`. |
| `AI_USAGE_LANGUAGE` | `auto`, `ko`, `en` 중 하나입니다. |
| `AI_USAGE_TIMEZONE` | `auto` 또는 `Asia/Seoul` 같은 IANA 시간대입니다. |
| `WORK_MONITOR_ENABLED` | `1`이면 `/work`와 작업 완료 감시를 켭니다. |
| `WORK_IDLE_SECONDS` | 로컬 로그에서 새 활동이 없을 때 작업 완료로 추정하기까지 기다리는 시간입니다. 기본값은 `600`초입니다. |
| `WORK_INCLUDE_SUMMARY` | 기본값은 `0`입니다. `1`로 명시하면 작업 완료 알림 본문과 임베드에 최종 응답에서 추출한 요약을 포함합니다. |
| `WORK_COMPLETION_COOLDOWN_SECONDS` | 같은 세션의 추정 완료 알림을 다시 보내지 않는 시간입니다. 기본값은 `3600`초입니다. |
| `WORK_PROVIDER_COMPLETION_COOLDOWN_SECONDS` | 같은 제공자의 추정 완료 알림이 너무 촘촘히 반복되지 않도록 막는 시간입니다. 기본값은 `300`초입니다. |
| `RESUME_QUEUE_ENABLED` | `1`이면 로컬 복구 큐 기능을 켭니다. 기본값은 `0`입니다. |

.env와 .alert_state.json은 비밀/상태 파일이므로 Git에 올리지 마세요.

## 실행

1회 리포트 확인:

```bat
python llm_report.py --dry-run
```

1회 리포트 전송:

```bat
python llm_report.py
```

가장 쉬운 실행:

```bat
LLM_report_bot.bat
```

실행 후 트레이와 봇 상태를 확인하는 작은 창이 뜨며, 몇 초 뒤 자동으로 닫힙니다.

콘솔 로그를 보면서 문제를 확인할 때만 디버그 실행:

```bat
run_llm_report_tray_debug.bat
```

Windows 로그인 시 자동 실행 등록:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_startup.ps1
```

자동 실행 해제:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_startup.ps1
```

최근 로그 보기:

```bat
tail_llm_report_logs.bat
```

트레이 메뉴의 `로그 열기`도 같은 실시간 로그 창을 엽니다. 이 창은 `ERROR/CRITICAL`을 빨간색, `WARNING`을 주황색, `INFO`를 회색으로 표시합니다. 실제 로그 파일은 `logs\llm_report_bot.log`에 UTF-8로 저장됩니다.

## Discord 명령

```text
/help
```

현재 등록된 LLM 봇 명령어와 설명을 표시합니다. 이후 새 슬래시 명령을 추가하면 이 목록에도 자동으로 반영됩니다.

```text
/status
```

봇 가동 시간, 작업 감시 상태, 진행 중인 작업 수만 개인 응답으로 표시합니다. 프롬프트와 작업 요약은 포함하지 않습니다.

```text
/settings
```

언어·시간대·Claude 추정 기준, 작업 감시 주기와 완료 판정 기준, 알림 연결 상태,
접근 제한 범위, 복구 큐 상태를 개인 응답으로 표시합니다. 토큰이나 웹훅 URL,
실제 허용 ID, 파일 경로는 노출하지 않고 설정 여부와 허용 개수만 보여줍니다.

```text
/usage
```

현재 Claude Code/Codex 사용량 리포트를 요청한 사용자에게만 embed로 응답합니다. Claude의 정확한 사용률은 Claude 앱의 `/usage`가 기준이고, 이 봇의 Claude 퍼센트는 로컬 로그 기반 추정치입니다.

```text
/work
```

현재 감시 중인 LLM 작업이 있는지, 진행 시간이 얼마나 됐는지 요청한 사용자에게만 표시합니다. 완료 알림에는 기본적으로 제공자 이름, 작업 시간 등 상태 정보만 보냅니다. 최종 응답에서 추출한 요약도 보내려면 `WORK_INCLUDE_SUMMARY=1`로 설정하세요.

Claude/Codex 로컬 로그 감시는 실제 완료 이벤트가 없는 fallback입니다. 기본값 기준으로 10분 동안 새 활동이 없을 때만 완료로 추정하고, 같은 세션은 1시간, 같은 제공자는 5분 동안 추정 완료 알림을 반복하지 않습니다. Codex는 메인 세션만 감시하고 서브 에이전트와 guardian 세션의 완료 알림은 보내지 않습니다. `llm_work_event.py complete`처럼 명시적으로 들어온 완료 이벤트는 즉시 알림을 보냅니다.

## 범용 작업 이벤트

Gemini, Grok, 자체 스크립트 같은 다른 도구도 로컬 이벤트 브리지를 호출하면 `/work`와 완료 감시에 잡힙니다.

```bat
python llm_work_event.py start --provider Gemini --session-id job-123
python llm_work_event.py complete --provider Gemini --session-id job-123 --summary "테스트와 배포 설정을 완료했습니다."
```

이벤트는 `logs\work_events.jsonl`에만 기록됩니다.

## 복구 큐

복구 큐는 Discord 명령으로 임의의 시스템 명령을 실행하지 않습니다. 로컬에서 직접 등록한 명령만 실행 대상입니다.

```bat
python queue_resume.py enqueue --provider Codex --session-id my-session --when-codex-recovers -- -- codex.cmd exec resume my-session "Continue the queued task."
python queue_resume.py list
python queue_resume.py cancel TASK_ID
```

## 주의

- 이 도구는 `~/.claude`와 `~/.codex`의 로컬 로그를 읽습니다. Claude/Codex를 실제로 쓰는 PC에서 실행해야 합니다.
- 같은 Discord 봇 토큰으로 여러 프로세스를 동시에 실행하면 게이트웨이 연결 충돌이 날 수 있습니다.
- Discord 봇 토큰이나 웹훅 URL을 README, 코드, 스크린샷, 이슈에 공개하지 마세요.


## 검증

외부 패키지 없이 실행 가능한 단위 테스트:

```powershell
python -S -B -m unittest discover -s tests -v
```

단위 테스트는 임시 로그와 모의 객체를 사용합니다. Discord 연결·실제 트레이 UI·시작프로그램 등록을 검증하는 테스트는 아닙니다.

런타임 의존성은 `requirements.txt`에 버전 범위로 기록되어 있으며 고정 버전 잠금 파일은 아닙니다.
새로운 환경에서 사용할 패키지는 설치 전에 해당 버전의 출처와 소스를 확인하세요.

공개 전 코드 점검 범위와 남은 제한은 [SECURITY_REVIEW.md](SECURITY_REVIEW.md)에 기록했습니다.
