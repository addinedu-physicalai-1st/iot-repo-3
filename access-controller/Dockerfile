# 1. 베이스 이미지 설정 (ESP32 환경 지원)
FROM egenie66/micro-ros:esp32

# 2. 작업 디렉토리 설정
# WORKDIR /root/microros

# 3. 환경 변수 고정 (docker run -e 옵션들을 이미지에 내장)
# ENV ROS_DOMAIN_ID=25
# ENV FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/disable_shm.xml
# ENV SHELL=/bin/bash

# 4. DDS 설정 파일 복사
# 빌드하려는 Dockerfile과 같은 폴더에 disable_shm.xml 파일이 있어야 합니다.
# COPY disable_shm.xml /tmp/disable_shm.xml

# 5. 소스 코드 마운트를 위한 디렉토리 구조 미리 생성
# (실행 시 -v 옵션으로 호스트의 코드를 연결할 지점입니다)
# RUN mkdir -p /root/microros/firmware/freertos_apps/apps/FactoryDoor_service

# 6. 추가 유틸리티 설치 (필요한 경우)
# RUN apt-get update && apt-get install -y vim screen && rm -rf /var/lib/apt/lists/*

# 7. 기본 실행 명령
CMD ["bash"]