# KS X 4506 EW11

EW11 RS485-to-TCP 장치를 통해 KS X 4506 월패드 장치를 Home Assistant에서 제어하는 커스텀 통합입니다.

현재 조명, 콘센트, 난방, 가스밸브 닫기, 계량 센서 일부를 지원합니다. 실제 아파트 월패드 패킷을 기반으로 개발 중인 프로젝트이므로, 설치 후 장치별 실측 확인이 필요합니다.

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

## 미지원 패킷 제보

아직 지원하지 않는 장치나 패킷은 진단 데이터로 제보할 수 있습니다.

1. 벽패드 또는 기존 앱에서 문제의 동작을 실행합니다.
2. Home Assistant에서 `설정` -> `기기 및 서비스` -> `KS X 4506 EW11`로 이동합니다.
3. `Download diagnostics`를 눌러 진단 JSON을 내려받습니다.
4. GitHub에서 `Unsupported packet report` 이슈를 생성하고 진단 JSON을 붙여 넣습니다.

또는 `Unsupported Packets` 진단 센서의 속성에서 `unsupported_packets` 내용을 복사해도 됩니다.

제보 시 다음 정보가 있으면 장치 지원을 추가하기 쉽습니다.

- 어떤 동작을 했는지
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
- 아직 해석되지 않은 장치는 Unknown 진단 센서로 먼저 노출될 수 있습니다.

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
| `0x33` | 현관 패널 | `sensor` | 읽기 전용 | 일괄소등, 엘리베이터 호출, 거실 조명 제어는 실측 전까지 버튼을 만들지 않습니다. |
| `0x36` | 난방/온도조절 | `climate`, `switch` | 일부 지원 | 난방 on/off와 정수 단위 설정온도를 제공합니다. |
| `0x39` | 콘센트/대기전력 차단 | `switch`, `sensor`, `binary_sensor` | 지원 | 콘센트 on/off, 전력, auto cut, threshold, overload 상태를 노출합니다. |
| `0x40` | 공동현관 | `sensor` | 읽기 전용 | 공동현관 이벤트로 분류합니다. 공유 출입 제어라 열기 버튼은 기본 제공하지 않습니다. |
| `0x60` | 미확인 센서 | `sensor` | 읽기 전용 | 1바이트 응답을 raw 값으로 노출합니다. 의미는 추가 실측 필요입니다. |

세부 관측 패킷과 미확정 항목은 [Observed Device Inventory](docs/observed-device-inventory.md)를 참고하세요.

## 개발 상태

현재 구현 범위는 다음과 같습니다.

- EW11 TCP client + 재연결/타임아웃
- RS485 프레임 경계 처리
- KS X 4506 파서
- 체크섬 검증
- 제어 명령 패킷 빌더
- 자동 탐지 레지스트리 + Unknown 진단 센서
- Home Assistant custom integration
- 명령 큐 + 재시도 + ACK 대기
- 위험 동작 안전가드

## 라이선스

MIT
