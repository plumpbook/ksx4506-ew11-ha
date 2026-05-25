# KS X 4506 EW11 → Home Assistant Integration (WIP)

EW11(RS485→TCP)로 수신한 KS X 4506 프레임을 파싱하여 Home Assistant 디바이스/엔티티를 자동 등록/제어하는 커스텀 인티그레이션입니다.

## 현재 구현 범위 (v0.1.0)
- EW11 TCP client + 재연결/타임아웃
- RS485 프레임 경계 처리 (STX/ETX + 길이 기반)
- KS X 4506 파서 (addr/cmd/len/payload/checksum)
- 체크섬 검증 (SUM8 기본, XOR8 옵션)
- 제어 명령 패킷 빌더
- 자동 탐지 레지스트리 + Unknown 진단 센서
- Home Assistant custom integration
  - config_flow
  - coordinator
  - light/switch/climate/fan/sensor 플랫폼
- 명령 큐 + 재시도 + ACK 대기
- 위험 동작 안전가드(가스밸브 기본 잠금)

## 지원 장치 현황

아래 표는 실제 EW11/HA 테스트 환경에서 관측한 패킷과 현재 구현 상태 기준입니다.

| Device ID | 장치 분류 | HA 엔티티 | 제어 | 상태 |
| --- | --- | --- | --- | --- |
| `0x0E` | 조명 | `light` | 지원 | 그룹 상태 패킷을 채널별 조명으로 분해하고, 개별 sub ID로 제어합니다. |
| `0x12` | 가스 밸브 | `valve`, `binary_sensor` | 닫기만 지원 | 안전상 열기/토글은 제공하지 않습니다. 상태 응답은 추가 실측이 필요합니다. |
| `0x30` | 통합 계량 | `sensor` | 읽기 전용 | 전기, 수도, 가스, 온수, 난방 계량의 순간/누적값을 관측 또는 상태 요청 응답 기반으로 센서로 제공합니다. |
| `0x33` | 현관 패널 | `sensor` | 읽기 전용 | 일괄소등, 엘리베이터 호출, 거실 조명 제어가 물리적으로 있으나 제어 패킷 실측 전까지 버튼은 만들지 않습니다. |
| `0x36` | 난방/온도조절 | `climate`, `switch` | 일부 지원 | 그룹 상태를 zone별 climate로 분해합니다. 난방 on/off와 0.5도 단위 설정온도를 제공합니다. |
| `0x39` | 콘센트/대기전력 차단 | `switch`, `sensor`, `binary_sensor` | 지원 | 그룹 상태 패킷을 물리 콘센트별로 분해하고, `39-11` 등 개별 sub ID로 제어합니다. 전력/auto cut/threshold/overload 상태를 노출합니다. |
| `0x40` | 공동현관 | `sensor` | 읽기 전용 | 공동현관 이벤트로 분류합니다. 공유 출입 제어라 열기 버튼은 기본 제공하지 않습니다. |
| `0x60` | 미확인 센서 | `sensor` | 읽기 전용 | 1바이트 응답을 raw 값으로만 노출합니다. 의미는 추가 실측 필요입니다. |

세부 관측 패킷과 미확정 항목은 [Observed Device Inventory](docs/observed-device-inventory.md)에 정리합니다.

## 설치
1. 이 저장소를 HA `config/custom_components/ksx4506_ew11`에 복사
2. Home Assistant 재시작
3. 설정 → 기기 및 서비스 → 통합 추가 → `KS X 4506 EW11`
4. EW11 IP/Port 입력 (기본 8899)

## EW11 권장 설정
- TCP Server 모드
- Baud: 월패드 버스 설정과 동일 (예: 9600 8N1)
- 패킷 병합/분할 비활성
- Keepalive 활성

## 트러블슈팅
- 프레임 파싱 실패: checksum mode(SUM8/XOR8), STX/ETX 확인
- 엔티티 미생성: unknown_devices 센서에서 raw frame 확인
- 지연/끊김: EW11 keepalive 및 네트워크 상태 점검

## 라이선스
MIT
