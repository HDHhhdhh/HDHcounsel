세빈 긴급복구 전용 counsel-note 원클릭 설치 안내

이 ZIP은 세빈 PC에서 counsel-note 폴더가 삭제되었을 때 다시 설치하기 위한 긴급 복구 전용 패키지입니다.
일반 실사용 배포 ZIP과 마찬가지로 Google Docs 매핑, Apps Script URL, admin 설정이 들어 있는 data/students 설정 폴더가 포함되어 있습니다.

절대 주의:
- 이 ZIP은 세빈 PC 전용입니다.
- 실사용에 필요한 data/students 학생 설정 데이터가 포함됩니다.
- Google Docs 문서, Apps Script 배포본, admin 서버 데이터는 이 설치로 수정되지 않습니다.
- data/local_consumed_admin_notes.json은 포함되어 있지 않습니다. 이 기록은 새로 시작해도 됩니다.
- Codex CLI 인증 파일, 토큰, 캐시는 ZIP에 포함되어 있지 않습니다.
- Codex CLI는 기존 PC 로그인 상태를 사용합니다. 앱 폴더를 지워도 보통 로그인은 유지됩니다. 정리본 생성이 안 되면 Codex CLI 로그인 상태를 확인해야 합니다.

사용 방법:
1. ZIP 압축을 풉니다.
2. 압축을 푼 폴더 안의 세빈_긴급복구_원클릭설치.bat 파일을 더블클릭합니다.
3. 설치가 끝나면 앱이 자동으로 실행됩니다.
4. 앱이 안 열리거나 오류가 나면 바탕화면에 생성된 counsel-note-diagnostic-*.zip 파일과 오류 화면 캡처를 보내주세요.

설치 동작:
- 기본 설치 위치는 바탕화면의 counsel-note 폴더입니다.
- 기존 counsel-note 폴더가 있으면 삭제하지 않고 counsel-note_OLD_YYYYMMDD-HHMMSS 이름으로 자동 백업합니다.
- 새 counsel-note 폴더에 앱 파일과 data/students 설정을 복사합니다.
- install_first.bat을 실행해 Python 가상환경과 필요한 패키지를 설치합니다.
- 설치 후 운영 진단과 import 검사를 실행합니다.
- 운영 진단에서는 codex 명령이 PATH에서 잡히는지와 codex --version 실행 여부만 확인합니다.
- Codex CLI를 새로 설치하거나 로그인시키지 않습니다.
- 실패하면 진단 패키지를 자동 생성합니다.

한 줄 요약:
ZIP 압축을 풀고 세빈_긴급복구_원클릭설치.bat만 더블클릭하세요.
