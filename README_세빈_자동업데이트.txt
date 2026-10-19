세빈 자동 업데이트 안내

세빈 PC에서는 앞으로 가능하면 세빈_업데이트_확인.bat만 실행하세요.

사용 방법:
1. counsel-note 앱과 브라우저를 닫습니다.
2. counsel-note 폴더 안의 세빈_업데이트_확인.bat을 더블클릭합니다.
3. 새 버전이 있으면 안내를 확인하고 적용합니다.
4. 업데이트가 끝나면 앱을 다시 실행합니다.

자동 업데이트 방식:
- 공유 폴더의 latest.json을 읽어 최신 update ZIP을 확인합니다.
- ZIP을 로컬 임시 폴더로 복사한 뒤 sha256을 검증합니다.
- 업데이트 전 현재 counsel-note 폴더를 counsel-note_BACKUP_YYYYMMDD-HHMMSS로 백업합니다.
- update ZIP의 payload만 현재 앱 폴더에 적용합니다.
- 실사용에 필요한 data/students 학생 설정 데이터도 함께 적용합니다.
- data/local_consumed_admin_notes.json도 덮어쓰지 않습니다.
- 기존 로그, CSV 결과, 녹음, 전사 파일은 건드리지 않습니다.

공유 폴더 경로:
- 기본 공유 폴더 경로는 스크립트 안에 들어 있습니다.
- 공유 폴더 위치가 바뀌면 data/local_update_source.txt 파일에 공유 폴더 경로만 한 줄로 적어두세요.
- 이 파일은 data/students 안에 두지 않습니다.

실패 시:
- 가능하면 백업 폴더에서 복구를 시도합니다.
- 바탕화면에 counsel-note-diagnostic-*.zip이 생성될 수 있습니다.
- diagnostic ZIP과 오류 화면 캡처를 함께 전달하세요.

주의:
- Google Docs 저장 요청은 자동 업데이트 중 실행하지 않습니다.
- admin POST/PATCH/DELETE는 실행하지 않습니다.
- Apps Script 배포는 자동으로 하지 않습니다.
- Codex CLI는 기존 PC 로그인 상태를 사용합니다.
