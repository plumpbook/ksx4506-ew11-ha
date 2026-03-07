# 트러블슈팅

## 1) 엔티티가 안 생김
- unknown diagnostic 센서 raw hex 확인
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
