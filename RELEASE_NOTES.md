# Release Notes

## v0.2.0
- HACS 설치와 업데이트에 맞춘 저장소 메타데이터와 문서를 정리했습니다.
- 조명, 콘센트, 난방, 가스, 계량, 현관, 공동현관 장치의 자동 발견과 엔티티 이름을 정리했습니다.
- 미지원 패킷은 자동 장치 생성 대신 `Unsupported Packets` 진단 센서와 diagnostics JSON에 기록하도록 변경했습니다.
- 기존에 생성된 unknown 장치와 엔티티는 config entry 삭제 시 registry cleanup으로 제거되도록 개선했습니다.
- 조명 그룹 상태 패킷을 채널별 상태로 분해하고, 개별 조명 제어 시 기존 채널 상태를 보존하도록 보정했습니다.
- 콘센트 그룹 패킷을 개별 채널 상태로 분해하도록 개선했습니다.
- ACK/상태 확인 기반 명령 재시도 흐름을 추가했습니다.

## v0.1.0
- EW11 TCP 수신/재연결 기본 구현
- KS X 4506 프레임 파서/빌더 기본 구현
- Home Assistant 커스텀 인티그레이션 초기 버전
- light/switch/climate/fan/sensor 플랫폼 초안
- unknown diagnostic 센서 추가
- 가스밸브 안전가드(기본 차단) 적용

## Known gaps
- 실환경 캡처 기반 cmd/type 매핑 정밀화 필요
- ACK/NAK 시맨틱은 벤더 구현별 보정 필요
- 장치별 payload 디코딩 룰 확장 필요
