# KS X 4506 EW11

EW11 RS485-to-TCP 장치를 통해 KS X 4506 월패드 장치를 Home Assistant에서 제어하는 커스텀 통합입니다.

현재 조명, 콘센트, 난방, 가스밸브 닫기, 계량 센서, 현관 패널, 공동현관 이벤트 일부를 지원합니다. 실제 아파트 월패드 패킷을 기반으로 개발 중인 프로젝트이므로, 설치 후 장치별 실측 확인이 필요합니다.

## 설치 전 확인

- Home Assistant에서 백업을 먼저 생성하세요.
- EW11은 Home Assistant에서 접근 가능한 로컬 IP를 사용해야 합니다.
- 하나의 EW11에 여러 Home Assistant 인스턴스가 동시에 연결되지 않도록 하세요.
- EW11은 TCP Server 모드로 설정하는 것을 권장합니다.

## HACS로 설치

1. Home Assistant에서 `HACS`를 엽니다.
2. 우측 상단 메뉴에서 `Custom repositories`를 선택합니다.
3. Repository에 아래 주소를 입력합니다.

   ```text
   https://github.com/plumpbook/ksx4506-ew11-ha
   ```

4. Category는 `Integration`을 선택합니다.
5. `Add`를 누릅니다.
6. HACS에서 `KS X 4506 EW11`을 찾아 설치합니다.
7. Home Assistant를 재시작합니다.
8. `설정` -> `기기 및 서비스` -> `통합 추가`로 이동합니다.
9. `KS X 4506 EW11`을 선택합니다.
10. EW11 접속 정보를 입력합니다.

## 설정값

대부분의 환경에서는 `host`만 EW11 IP로 입력하고 나머지는 기본값을 사용하면 됩니다.

| 항목 | 기본값 | 설명 |
| --- | --- | --- |
| `host` | 없음 | EW11의 로컬 IP 주소 |
| `port` | `8899` | EW11 TCP 포트 |
| `timeout` | `3.0` | 연결 및 송신 타임아웃 |
| `retry` | `2` | TCP 송신 재시도 횟수 |
| `max_attempts` | `10` | 제어 명령 ACK/상태 확인 최대 시도 횟수 |
| `checksum` | `sum8` | 체크섬 방식 |
| `stx` | `02` | STX 프레임 시작 바이트 |
| `etx` | `03` | ETX 프레임 종료 바이트 |
| `gas_unlock` | `false` | 가스밸브 위험 동작 안전가드 해제 여부 |
| `expose_packet_samples` | `false` | 미지원 패킷 진단에 raw/payload hex 샘플을 포함할지 여부 |
| `packet_capture_enabled` | `false` | 최근 수신 패킷을 `Packet Capture` 센서 속성에 보관할지 여부 |
| `packet_capture_filter` | `33,40` | 캡처할 device id 목록. 예: `33`, `33,40`, `0x33,0x40`, `*` |
| `packet_capture_limit` | `20` | 최근 패킷 보관 개수 |

등록 후 `timeout`, `retry`, `max_attempts`, `gas_unlock`, `expose_packet_samples`, `packet_capture_*` 옵션은 통합의 `구성` 또는 `Options` 화면에서 변경할 수 있습니다. 기존 EW11 설정을 바꾸기 위해 `통합 추가`를 다시 누르면 같은 EW11 host/port와 충돌할 수 있습니다.

`host`, `port`, `checksum`, `stx`, `etx`는 연결/프레임 기준값이라 등록 후 옵션 화면에서는 변경하지 않습니다. 이 값이 바뀌면 기존 항목을 삭제한 뒤 다시 추가하세요.

## EW11 권장 설정

- Mode: TCP Server
- Port: `8899`
- Baudrate: 월패드 RS485 버스와 동일
- Data bits / parity / stop bits: 월패드 RS485 버스와 동일
- Keepalive: 활성화 권장
- 패킷 병합/분할 옵션: 비활성 권장

## 설치 후 확인

1. 벽패드 또는 기존 앱에서 조명, 콘센트, 난방을 한 번씩 조작합니다.
2. Home Assistant에 엔티티가 자동 생성되는지 확인합니다.
3. 먼저 조명 하나만 Home Assistant에서 켜고 끕니다.
4. 이후 콘센트, 난방 순서로 테스트합니다.

이 통합은 EW11로 들어오는 패킷을 기반으로 장치를 자동 발견합니다. 설치 직후 엔티티가 적게 보이면 벽패드나 기존 앱에서 장치를 한 번씩 조작해 보세요.

## 업데이트와 버전 확인

이 저장소는 `v0.2.0` 같은 semantic version GitHub release로 배포합니다.

HACS에서 난수처럼 보이는 값이 표시되면 release가 아니라 기본 브랜치의 commit 기준으로 설치된 상태일 수 있습니다. HACS에서 저장소를 새로 고침한 뒤 표시 버전이 최신 release와 일치하는지 확인하세요.

업데이트 후에는 Home Assistant를 재시작해야 새 통합 코드가 적용됩니다.

## 미지원 패킷 제보

아직 지원하지 않는 장치나 패킷은 진단 데이터로 제보할 수 있습니다. 진단 분류와 센서 속성의 의미는 [Packet Diagnostics](docs/packet-diagnostics.md)를 참고하세요.

기본 제보에는 raw 패킷 샘플이 포함되지 않습니다. 먼저 안전한 기본 diagnostics로 제보하고, 장치 분석에 raw 샘플이 꼭 필요할 때만 `expose_packet_samples`를 잠시 켜세요.

1. Home Assistant에서 `설정` -> `기기 및 서비스` -> `KS X 4506 EW11`로 이동합니다.
2. 해당 EW11 허브의 `Unsupported Packets` 센서 값 또는 속성의 `packets` 내용을 확인합니다.
3. 벽패드 또는 기존 앱에서 문제의 동작을 한 번 실행합니다.
4. `Download diagnostics`를 눌러 진단 JSON을 내려받습니다.
5. GitHub에서 `Unsupported packet report` 이슈를 생성하고 진단 JSON을 붙여 넣습니다.

`Unsupported Packets` 센서의 상태값은 반복 횟수가 아니라 미지원/후보 패킷 signature 수입니다. 총 관측 횟수는 센서 속성의 `total_seen`에서 확인할 수 있습니다.

센서 속성에서 먼저 아래 값을 확인하세요.

- `summary`: unsupported/candidate/unique 개수 요약
- `latest_unsupported_signature`: 최근 실제 미지원 패킷 요약
- `latest_candidate_signature`: 알려진 장치 ID지만 아직 등록하지 않은 후보 패킷 요약
- `top_unsupported_signatures`: 반복 횟수가 많은 미지원 패킷 요약
- `top_candidate_signatures`: 반복 횟수가 많은 후보 패킷 요약

`unsupported`는 아직 지원하지 않는 device id 또는 command입니다. `candidate`는 device id는 알려져 있지만 sub id나 payload가 아직 안전하게 장치로 등록될 만큼 확인되지 않은 패킷입니다. 자세한 내용이 필요하면 센서 속성의 `unsupported_packets`, `candidate_packets`, `packets` 내용을 복사하면 됩니다.

raw/payload hex 샘플은 장치 지원을 추가할 때 도움이 되지만, 집의 장치 구성과 동작 패턴을 드러낼 수 있습니다. 공개 GitHub 이슈에는 기본 진단 요약을 먼저 올리고, raw 샘플이 꼭 필요한 경우에만 아래 순서로 공유하세요.

1. `설정` -> `기기 및 서비스` -> `KS X 4506 EW11` -> EW11 허브의 `구성` 또는 `Options`로 이동합니다.
2. `expose_packet_samples`를 켭니다.
3. 문제의 동작을 한 번만 다시 실행합니다.
4. diagnostics를 다시 내려받습니다.
5. `expose_packet_samples`를 다시 끕니다.
6. 진단 JSON에서 위치, 이름, 실제 네트워크 주소, 계정명 등 공개하면 안 되는 정보를 제거한 뒤 공유합니다.

특정 동작의 패킷을 짧게 관찰하려면 HA 전체 debug 로그 대신 `packet_capture_enabled`를 잠시 켜세요. `packet_capture_filter`를 `33`처럼 좁히고 동작을 한 번 실행한 뒤, `Packet Capture` 센서의 `summary`, `latest_packet_signature`, `latest_unsupported_signature`, `latest_candidate_signature`, `unsupported_packets`, `candidate_packets`, `packets` 속성을 확인합니다. 관찰이 끝나면 `packet_capture_enabled`를 다시 끄세요.

제보에는 실제 집 주소, 동/호수, 개인 네트워크 주소, 외부 접속 주소, 계정명, 가족 이름을 넣지 마세요. 예시가 필요하면 `ew11.example.invalid` 같은 reserved hostname이나 `192.0.2.10` 같은 문서용 IP를 사용하세요.

제보 시 다음 정보가 있으면 장치 지원을 추가하기 쉽습니다.

- 어떤 동작을 어떤 순서로 했는지
- 벽패드 또는 아파트 시스템 제조사/모델
- Home Assistant 버전
- EW11 serial 설정

## 수동 설치

HACS를 사용하지 않는 경우:

1. 이 저장소의 `custom_components/ksx4506_ew11` 디렉터리를 Home Assistant의 아래 경로에 복사합니다.

   ```text
   /config/custom_components/ksx4506_ew11
   ```

2. Home Assistant를 재시작합니다.
3. `설정` -> `기기 및 서비스` -> `통합 추가`로 이동합니다.
4. `KS X 4506 EW11`을 선택합니다.
5. EW11 접속 정보를 입력합니다.

## 문제 해결

### 통합이 검색되지 않음

- Home Assistant를 재시작했는지 확인합니다.
- 브라우저 캐시를 새로고침합니다.
- 수동 설치라면 `/config/custom_components/ksx4506_ew11/manifest.json` 파일이 있는지 확인합니다.

### 엔티티가 적게 보임

- 벽패드 또는 기존 앱에서 장치를 한 번씩 조작합니다.
- Home Assistant 로그에서 `ksx4506_ew11` 메시지를 확인합니다.
- 아직 해석되지 않은 패킷은 장치로 자동 생성되지 않고 `Unsupported Packets` 진단 센서에 요약됩니다.

### 연결 실패

- EW11 IP와 포트가 맞는지 확인합니다.
- Home Assistant에서 EW11 IP로 접근 가능한지 확인합니다.
- 다른 Home Assistant 또는 테스트 데몬이 같은 EW11에 동시에 연결되어 있지 않은지 확인합니다.

## 지원 장치

아래 표는 실제 EW11/Home Assistant 테스트 환경에서 관측한 패킷과 현재 구현 상태 기준입니다.

| Device ID | 장치 분류 | HA 엔티티 | 제어 | 상태 |
| --- | --- | --- | --- | --- |
| `0x0E` | 조명 | `light` | 지원 | 그룹 상태 패킷을 채널별 조명으로 분해하고, 개별 sub ID로 제어합니다. |
| `0x12` | 가스 밸브 | `valve`, `binary_sensor` | 닫기만 지원 | 안전상 열기/토글은 기본 제공하지 않습니다. |
| `0x30` | 통합 계량 | `sensor` | 읽기 전용 | 전기, 수도, 가스, 온수, 난방 계량을 센서로 제공합니다. |
| `0x33` | 현관 패널 | `sensor`, `binary_sensor` | 읽기 전용 | 일괄소등/보조입력 상태 bit와 `Elevator Status` 센서의 `idle`/`calling`/`arrived` 상태를 노출합니다. 제어 버튼은 실측 전까지 만들지 않습니다. |
| `0x36` | 난방/온도조절 | `climate`, `switch` | 일부 지원 | 난방 on/off와 정수 단위 설정온도를 제공합니다. |
| `0x39` | 콘센트/대기전력 차단 | `switch`, `sensor`, `binary_sensor` | 지원 | 콘센트 on/off, 전력, auto cut, threshold, overload 상태를 노출합니다. |
| `0x40` | 공동현관 | `sensor` | 읽기 전용 | 공동현관 이벤트로 분류합니다. 공유 출입 제어라 열기 버튼은 기본 제공하지 않습니다. |
| `0x60` | 미확인 센서 | `sensor` | 읽기 전용 | 1바이트 응답을 raw 값으로 노출합니다. 의미는 추가 실측 필요입니다. |

장치별 상세 지원 범위는 [Device Support](docs/device-support.md), 세부 관측 패킷과 미확정 항목은 [Observed Device Inventory](docs/observed-device-inventory.md)를 참고하세요.

`0x33`의 `arrived`는 순간 이벤트입니다. 이후 `0x81` 대기 상태 패킷이 들어오면 `Elevator Status`가 다시 `idle`로 바뀔 수 있습니다. 자동화에서 반복 이벤트를 감지하려면 센서 속성의 `last_panel_event_seq`를 함께 확인하세요.

## 엔티티 정리 정책

이 통합은 업데이트 또는 항목 제거 시 오래된 registry 항목을 정리합니다. 이전 버전에서 생성되던 unknown 장치, 후보 패킷 장치, 콘센트 그룹 pseudo 장치, 난방 target-temperature number, 개별 thermostat ACK 장치, 이전 meter 이름은 현재 모델에 맞게 제거되거나 이름이 보정됩니다.

EW11 항목을 삭제하면 해당 config entry가 소유한 entity/device registry 항목도 제거됩니다. 같은 EW11을 다시 추가하면 현재 discovery 규칙으로 장치가 다시 생성됩니다.

## 개발 상태

현재 구현 범위는 다음과 같습니다.

- EW11 TCP client + 재연결/타임아웃
- RS485 프레임 경계 처리
- KS X 4506 파서
- 체크섬 검증
- 제어 명령 패킷 빌더
- 자동 탐지 레지스트리 + 미지원 패킷 진단 센서
- Home Assistant custom integration
- 명령 큐 + 재시도 + ACK 대기
- 위험 동작 안전가드

## 라이선스

MIT
