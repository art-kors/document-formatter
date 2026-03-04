sudo docker build -t fastapi-alpine .

# 3. Запустите контейнер
sudo docker run -p 8000:8000 fastapi-alpine