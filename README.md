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
