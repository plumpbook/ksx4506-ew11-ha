# 트러블슈팅

## 1) 엔티티가 안 생김
- `Unsupported Packets` 진단 센서에서 device/sub/cmd 요약 확인
- 센서 상태값은 signature 수이며, 반복 횟수는 속성의 `total_seen` 확인
- `candidate_packets`는 알려진 장치 ID지만 아직 등록하지 않은 sub id/payload입니다.
- `unsupported_packets`는 지원하지 않는 device id 또는 command입니다.
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
- `Unsupported Packets`는 누적 진단용이고, `Packet Capture`는 짧은 실측 캡처용입니다.
- `Packet Capture` 속성에서 `latest_packet_signature`, `latest_unsupported_signature`, `latest_candidate_signature`, `unsupported_packets`, `candidate_packets`, `packets`를 확인합니다.
- 장치 지원 추가에 미지원 패킷 raw 샘플이 꼭 필요할 때만 `expose_packet_samples`를 켭니다.
- 캡처가 끝나면 `packet_capture_enabled`와 `expose_packet_samples`를 다시 끕니다.
- 공개 이슈에 올리기 전 집 주소, 동/호수, 개인 식별 정보와 함께 캡처된 맥락을 제거하세요.

## 6) 예전 엔티티가 남아 있거나 사라짐
- 현재 버전은 legacy registry cleanup을 수행합니다.
- 이전 unknown 장치, invalid candidate 장치, 콘센트 그룹 pseudo 장치, 난방 target-temperature number, 개별 thermostat ACK 장치는 제거될 수 있습니다.
- EW11 항목을 삭제하면 해당 항목이 소유한 entity/device registry도 정리됩니다.
- 제거 후 다시 추가하면 현재 지원하는 장치만 새 discovery 규칙으로 생성됩니다.

## 7) 엘리베이터 상태가 금방 idle로 돌아감
- `0x33` 현관 패널의 도착 패킷은 순간 이벤트입니다.
- `Elevator Status`가 `arrived`가 된 직후 대기 상태 패킷이 들어오면 `idle`로 바뀔 수 있습니다.
- 자동화에서는 `last_elevator_event`, `last_panel_event_code`, `last_panel_event_seq` 속성을 함께 확인하세요.
