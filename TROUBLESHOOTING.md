# 트러블슈팅

## 1) 엔티티가 안 생김
- `Unsupported Packets` 진단 센서에서 device/sub/cmd 요약 확인
- 센서 상태값은 signature 수이며, 반복 횟수는 속성의 `total_seen` 확인
- checksum mode(sum8/xor8) 변경
- STX/ETX(02/03) 값 확인

## 2) 상태 반영 지연
- EW11 keepalive 켜기
- AP 절전/유선 구간 네트워크 점검
- timeout/retry 조정

## 3) 제어가 안 먹음
- cmd 매핑이 기기 벤더 확장과 다른 경우가 많음
- 실측 캡처로 `discovery.py` CMD_TYPE_MAP 보정 필요
- ACK 프레임 구조 확인 필요

## 4) 가스밸브 제어 차단됨
- 기본 안전가드 동작 정상
- config_flow의 `gas_unlock`를 명시적으로 켠 경우만 허용

## 5) raw 패킷 샘플이 필요함
- 기본 진단은 보안을 위해 raw/payload hex를 숨깁니다.
- 특정 device id만 짧게 볼 때는 `packet_capture_enabled`를 켜고 `packet_capture_filter`를 `33`처럼 좁힌 뒤 `Packet Capture` 센서 속성을 확인합니다.
- 장치 지원 추가에 미지원 패킷 raw 샘플이 꼭 필요할 때만 `expose_packet_samples`를 켭니다.
- 캡처가 끝나면 `packet_capture_enabled`와 `expose_packet_samples`를 다시 끕니다.
- 공개 이슈에 올리기 전 집 주소, 동/호수, 개인 식별 정보와 함께 캡처된 맥락을 제거하세요.
