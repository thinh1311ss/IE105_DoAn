from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import numpy as np
import cv2
import tensorflow as tf
import os
from dotenv import load_dotenv
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
import logging
from gmail_service import get_gmail_service
from googleapiclient.errors import HttpError
import time
from functools import wraps

# Cấu hình logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load biến môi trường
load_dotenv()

build_dir = os.path.normpath(r"C:\UIT\IE\IE105\DoAn\WEB_FIRE_DETECTION\FIRE_DETECTION\frontend\build")
static_dir = os.path.join(build_dir, "static")

app = Flask(__name__, static_folder=static_dir, template_folder=build_dir)
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=10 * 1024 * 1024)

# Cấu hình từ .env
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
PORT = int(os.getenv('PORT', 1311))
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')

# Kiểm tra biến môi trường
if not EMAIL_ADDRESS:
    logger.error("EMAIL_ADDRESS không được cấu hình trong .env")
    raise ValueError("Cần cấu hình EMAIL_ADDRESS trong .env")

# Tạo thư mục upload nếu chưa tồn tại
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load TFLite model
try:
    model_path = r"C:\UIT\IE\IE105\DoAn\MODEL\fire_detection4.tflite"
    if not os.path.exists(model_path):
        logger.error(f"Không tìm thấy mô hình tại: {model_path}")
        raise FileNotFoundError(f"Không tìm thấy mô hình tại: {model_path}")
    interpreter = tf.lite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    height, width = input_details[0]['shape'][1:3]
    logger.info(f"Đã tải mô hình TFLite với kích thước đầu vào: {height}x{width}")
except Exception as e:
    logger.error(f"Lỗi khi tải mô hình TFLite: {e}")
    raise

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    logger.debug(f"Thư mục build: {build_dir}")
    logger.debug(f"Đường dẫn yêu cầu: {path}")

    full_path = os.path.join(build_dir, path) if path else os.path.join(build_dir, 'index.html')
    logger.debug(f"Full path kiểm tra: {full_path}")
    if os.path.exists(full_path) and os.path.isfile(full_path):
        logger.info(f"Phục vụ tệp: {full_path}")
        try:
            return send_from_directory(build_dir, path if path else 'index.html')
        except Exception as e:
            logger.error(f"Lỗi khi phục vụ tệp {path}: {str(e)}")
            return jsonify({"error": f"Lỗi khi phục vụ tệp {path}: {str(e)}"}), 500
    else:
        index_path = os.path.join(build_dir, 'index.html')
        logger.debug(f"Kiểm tra index.html tại: {index_path}")
        if os.path.exists(index_path):
            logger.info(f"Phục vụ index.html từ: {index_path}")
            try:
                return send_from_directory(build_dir, 'index.html')
            except Exception as e:
                logger.error(f"Lỗi khi phục vụ index.html: {str(e)}")
                return jsonify({"error": f"Lỗi khi phục vụ index.html: {str(e)}"}), 500
        else:
            logger.error(f"Không tìm thấy index.html tại: {index_path}")
            return jsonify({"error": f"Không tìm thấy index.html tại {index_path}"}), 404

@app.route('/server')
def serve_server():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    public_dir = os.path.join(base_dir, '..', 'frontend', 'public')
    return send_from_directory(public_dir, 'sever.html')

@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    join_room('server')

@socketio.on('join')
def handle_join(data):
    logger.info(f"Client {request.sid} joined with role: {data['role']}")
    join_room('server')

@socketio.on('offer')
def handle_offer(data):
    logger.info(f"Received offer from {request.sid}: {data}")
    emit('offer', {'clientId': request.sid, 'offer': data['offer']}, broadcast=True)

@socketio.on('answer')
def handle_answer(data):
    logger.info(f"Received answer for {data['clientId']}: {data}")
    emit('answer', {'answer': data['answer']}, to=data['clientId'])

@socketio.on('ice-candidate')
def handle_ice_candidate(data):
    logger.info(f"Received ICE candidate for {data['clientId']}: {data}")
    emit('ice-candidate', {'candidate': data['candidate']}, to=data['clientId'])

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")
    leave_room('server')
    emit('client-disconnected', request.sid, broadcast=True)

@socketio.on('webcam_frame')
def handle_webcam_frame(data):
    logger.info(f"Nhận webcam_frame từ client {data['clientId']}, kích thước dữ liệu: {len(data['frame'])}")
    logger.debug(f"Dữ liệu khung hình đầu: {data['frame'][:50]}")
    try:
        if not (data['frame'].startswith('data:image/png;base64,') or data['frame'].startswith('data:image/jpeg;base64,')):
            logger.error("Định dạng khung hình không hợp lệ")
            emit('prediction_result', {'error': 'Định dạng khung hình không hợp lệ'}, to=data['clientId'])
            return

        frame_data = base64.b64decode(data['frame'].split(',')[1])
        logger.info("Đã giải mã base64 thành công")
        npimg = np.frombuffer(frame_data, np.uint8)
        img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            logger.error("Không thể giải mã khung hình")
            emit('prediction_result', {'error': 'Không thể giải mã khung hình'}, to=data['clientId'])
            return

        logger.info(f"Giải mã khung hình thành công, kích thước: {img.shape}")
        is_fire, score = predict_fire(img)
        result = "fire" if is_fire else "no_fire"
        logger.info(f"Kết quả dự đoán: {result}, score: {score}")

        # Gửi frame tới server để hiển thị
        emit('frame', {'clientId': data['clientId'], 'image': data['frame'], 'type': 'webcam'}, room='server')

        # Gửi kết quả dự đoán
        prediction_data = {
            'clientId': data['clientId'],
            'result': result,
            'score': score,
            'message': "Đang phân tích..." if is_fire else "Không phát hiện cháy"
        }
        logger.info(f"Phát prediction_result tới server room: {prediction_data}")
        emit('prediction_result', prediction_data, room='server')
        logger.info(f"Phát prediction_result tới client {data['clientId']}: {prediction_data}")
        emit('prediction_result', prediction_data, to=data['clientId'])
    except Exception as e:
        logger.error(f"Lỗi xử lý khung hình: {str(e)}")
        emit('prediction_result', {'error': str(e)}, to=data['clientId'])

@socketio.on('pi_frame')
def handle_pi_frame(data):
    logger.info(f"Nhận pi_frame từ Raspberry Pi {data['clientId']}, kích thước dữ liệu: {len(data['frame'])}")
    logger.debug(f"Dữ liệu khung hình đầu: {data['frame'][:50]}")
    try:
        if not (data['frame'].startswith('data:image/png;base64,') or data['frame'].startswith('data:image/jpeg;base64,')):
            logger.error("Định dạng khung hình không hợp lệ")
            emit('pi_prediction_result', {'error': 'Định dạng khung hình không hợp lệ'}, to=data['clientId'])
            return

        frame_data = base64.b64decode(data['frame'].split(',')[1])
        logger.info("Đã giải mã base64 thành công")
        npimg = np.frombuffer(frame_data, np.uint8)
        img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            logger.error("Không thể giải mã khung hình")
            emit('pi_prediction_result', {'error': 'Không thể giải mã khung hình'}, to=data['clientId'])
            return

        logger.info(f"Giải mã khung hình thành công, kích thước: {img.shape}")
        is_fire, score = predict_fire(img)
        result = "fire" if is_fire else "no_fire"
        logger.info(f"Kết quả dự đoán: {result}, score: {score}")

        # Gửi frame tới server để hiển thị
        emit('frame', {'clientId': data['clientId'], 'image': data['frame'], 'type': 'raspberry_pi'}, room='server')

        # Gửi kết quả dự đoán
        prediction_data = {
            'clientId': data['clientId'],
            'result': result,
            'score': score,
            'message': "Đang phân tích..." if is_fire else "Không phát hiện cháy"
        }
        logger.info(f"Phát pi_prediction_result tới server room: {prediction_data}")
        emit('pi_prediction_result', prediction_data, room='server')
        logger.info(f"Phát pi_prediction_result tới client {data['clientId']}: {prediction_data}")
        emit('pi_prediction_result', prediction_data, to=data['clientId'])
    except Exception as e:
        logger.error(f"Lỗi xử lý khung hình từ Raspberry Pi: {str(e)}")
        emit('pi_prediction_result', {'error': str(e)}, to=data['clientId'])

@socketio.on('stop')
def handle_stop(data):
    logger.info(f"Nhận sự kiện stop từ client {data['clientId']}, lastResult: {data['lastResult']}")
    try:
        if not (data['frame'].startswith('data:image/png;base64,') or data['frame'].startswith('data:image/jpeg;base64,')):
            logger.error("Định dạng khung hình cuối không hợp lệ")
            emit('prediction_result', {'error': 'Định dạng khung hình cuối không hợp lệ'}, to=data['clientId'])
            return

        frame_data = base64.b64decode(data['frame'].split(',')[1])
        logger.info("Đã giải mã base64 khung hình cuối thành công")
        npimg = np.frombuffer(frame_data, np.uint8)
        img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            logger.error("Không thể giải mã khung hình cuối")
            emit('prediction_result', {'error': 'Không thể giải mã khung hình cuối'}, to=data['clientId'])
            return

        logger.info(f"Giải mã khung hình cuối thành công, kích thước: {img.shape}")
        is_fire, score = predict_fire(img)
        result = "fire" if is_fire else "no_fire"
        logger.info(f"Kết quả dự đoán frame cuối: {result}, score: {score}")

        if is_fire:
            logger.info(f"Phát hiện cháy ở frame cuối, chuẩn bị gửi email đến: {EMAIL_ADDRESS}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], f"webcam_fire_{timestamp}.jpg")
            cv2.imwrite(img_path, img)
            logger.info(f"Đã lưu ảnh cháy tại: {img_path}")
            success = send_fire_alert(EMAIL_ADDRESS, score, img_path)
            if success:
                logger.info(f"Đã gửi email thành công đến {EMAIL_ADDRESS}")
            else:
                logger.error(f"Gửi email thất bại cho {EMAIL_ADDRESS}")
        else:
            logger.info(f"Không gửi email: is_fire={is_fire}")

        prediction_data = {
            'clientId': data['clientId'],
            'result': result,
            'score': score,
            'message': "Cảnh báo đã được gửi qua email" if is_fire and success else "Không phát hiện cháy"
        }
        logger.info(f"Phát prediction_result cuối cùng tới server room: {prediction_data}")
        emit('prediction_result', prediction_data, room='server')
        logger.info(f"Phát prediction_result cuối cùng tới client {data['clientId']}: {prediction_data}")
        emit('prediction_result', prediction_data, to=data['clientId'])
    except Exception as e:
        logger.error(f"Lỗi xử lý sự kiện stop: {str(e)}")
        emit('prediction_result', {'error': str(e)}, to=data['clientId'])

def predict_fire(image):
    try:
        logger.debug(f"Hình ảnh gốc: {image.shape}")
        if image.size == 0:
            logger.warning("Ảnh đầu vào rỗng")
            return False, 0.0

        # Chuẩn bị ảnh đầu vào
        image = cv2.resize(image, (width, height))
        image_float = image.astype(np.float32) / 255.0
        image = np.expand_dims(image_float, axis=0)
        logger.debug(f"Hình ảnh sau xử lý: {image.shape}")

        # Đặt tensor đầu vào
        interpreter.set_tensor(input_details[0]['index'], image)
        interpreter.invoke()

        # Lấy tensor đầu ra và giải phóng tham chiếu ngay lập tức
        output = interpreter.get_tensor(output_details[0]['index'])
        raw_score = float(output[0][0])
        output = None  # Giải phóng tham chiếu

        logger.info(f"Điểm dự đoán thô: {raw_score}")
        if raw_score < 0 or raw_score > 1:
            score = 1 / (1 + np.exp(-raw_score))
            logger.info(f"Score sau sigmoid: {score}")
        else:
            score = raw_score

        threshold = 0.5
        is_fire = score > threshold
        logger.info(f"Ngưỡng: {threshold}, Kết quả: {'fire' if is_fire else 'no_fire'}, Score: {score}")
        return is_fire, score
    except Exception as e:
        logger.error(f"Lỗi trong predict_fire: {e}")
        return False, 0.0

def send_fire_alert(email, score, image_path=None):
    try:
        service = get_gmail_service()
        if not service:
            logger.error("Không thể lấy service từ gmail_service.py")
            return False

        message = MIMEMultipart()
        message['To'] = email
        message['From'] = EMAIL_ADDRESS
        message['Subject'] = 'CẢNH BÁO: Phát hiện cháy!'

        text_content = f"""
        CẢNH BÁO CHÁY
        Độ tin cậy: {score*100:.2f}%
        Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        message.attach(MIMEText(text_content, 'plain'))

        html_content = f"""
        <h2 style="color: red;">🔥 CẢNH BÁO CHÁY 🔥</h2>
        <p>Độ tin cậy: <strong>{score*100:.2f}%</strong></p>
        <p>Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        message.attach(MIMEText(html_content, 'html'))

        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as img_file:
                img_data = img_file.read()
            mime_image = MIMEImage(img_data, name='fire_alert.jpg')
            mime_image.add_header('Content-Disposition', 'attachment', filename='fire_alert.jpg')
            message.attach(mime_image)
            logger.info(f"Đã đính kèm ảnh: {image_path}")

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = {'raw': encoded_message}

        logger.info(f"Thực hiện gửi email đến {email}")
        result = service.users().messages().send(userId="me", body=send_message).execute()
        logger.info(f"Đã gửi email đến {email}, Message ID: {result['id']}")
        return True

    except HttpError as e:
        logger.error(f"Lỗi HTTP khi gửi email: {str(e)} - Mã lỗi: {e.resp.status}")
        return False
    except Exception as e:
        logger.error(f"Lỗi khi gửi email: {str(e)}")
        return False

@app.route('/api/predict', methods=['POST'])
def predict():
    logger.info("Nhận yêu cầu tại /api/predict")
    logger.info(f"Request files: {request.files}")
    logger.info(f"Request form: {request.form}")
    if 'file' not in request.files:
        logger.error("Không có tệp trong yêu cầu")
        return jsonify({"error": "Không có tệp trong yêu cầu"}), 400
    file = request.files['file']
    filename = file.filename.lower()
    ext = os.path.splitext(filename)[1]
    try:
        if ext in ['.jpg', '.jpeg', '.png']:
            npimg = np.frombuffer(file.read(), np.uint8)
            img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                logger.error("Không thể giải mã ảnh")
                return jsonify({"error": "Không thể giải mã ảnh"}), 400
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], f"fire_check_{timestamp}{ext}")
            cv2.imwrite(img_path, img)
            logger.info(f"Đã lưu ảnh tại: {img_path}")
            is_fire, score = predict_fire(img)
        else:
            logger.error("Chỉ chấp nhận ảnh (jpg, jpeg, png)")
            return jsonify({"error": "Chỉ chấp nhận ảnh"}), 400
        result = "fire" if is_fire else "no_fire"
        logger.info(f"Kết quả dự đoán: {result}, điểm: {score}")
        if is_fire:
            logger.info(f"Gửi email từ {EMAIL_ADDRESS} đến {EMAIL_ADDRESS}")
            send_fire_alert(EMAIL_ADDRESS, score, img_path)
        return jsonify({
            "result": result,
            "score": score,
            "message": "Cảnh báo đã được gửi qua email" if is_fire else "Không phát hiện cháy",
            "image_path": img_path if ext in ['.jpg', '.jpeg', '.png'] else None
        })
    except Exception as e:
        logger.error(f"Lỗi trong route /api/predict: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_from_pi():
    start_time = time.time()
    logger.info(f"Nhận yêu cầu upload từ IP: {request.remote_addr}")
    
    # Lấy dữ liệu JSON
    data = request.get_json()
    required_fields = ['image', 'client_id', 'label']
    
    # Xác thực đầu vào
    if not data or not all(field in data for field in required_fields):
        logger.error(f"Thiếu các trường bắt buộc: {required_fields}")
        return jsonify({'error': 'Thiếu thông tin'}), 400
    
    try:
        # Xác thực ảnh base64
        image_data = data['image']
        if image_data.startswith('data:image/jpeg;base64,'):
            image_data = image_data.split(',')[1]
        try:
            base64.b64decode(image_data)
        except (base64.binascii.Error, ValueError):
            logger.error("Dữ liệu ảnh base64 không hợp lệ")
            return jsonify({'error': 'Dữ liệu ảnh base64 không hợp lệ'}), 400

        # Xác thực client_id
        client_id = data['client_id'].strip()
        if not client_id or len(client_id) > 50:  # Điều chỉnh giới hạn độ dài nếu cần
            logger.error(f"client_id không hợp lệ: {client_id}")
            return jsonify({'error': 'client_id không hợp lệ'}), 400

        # Chuẩn bị dữ liệu phát
        emit_data = {
            'clientId': client_id,
            'image': f'data:image/jpeg;base64,{image_data}' if not data['image'].startswith('data:image/jpeg;base64,') else data['image'],
            'type': 'raspberry_pi'
        }

        # Xác thực và phân tích nhãn
        label = data['label'].lower()
        if 'cháy' not in label and 'no fire' not in label:
            logger.error(f"Định dạng nhãn không hợp lệ: {label}")
            return jsonify({'error': 'Định dạng nhãn không hợp lệ'}), 400

        # Trích xuất điểm số
        try:
            score_str = label.split('(')[-1].replace('%', '').replace(')', '')
            score = float(score_str) / 100
            if not 0 <= score <= 1:
                raise ValueError("Điểm số ngoài phạm vi hợp lệ")
        except (ValueError, IndexError) as e:
            logger.error(f"Định dạng điểm số không hợp lệ trong nhãn: {label}, lỗi: {str(e)}")
            return jsonify({'error': 'Định dạng điểm số không hợp lệ'}), 400

        # Phát khung hình đến phòng server
        logger.info(f"Phát khung hình đến phòng server cho client: {client_id}")
        socketio.emit('frame', emit_data, room='server')

        # Phát kết quả dự đoán
        prediction_data = {
            'clientId': client_id,
            'result': 'fire' if 'cháy' in label else 'no_fire',
            'score': score,
            'message': data['label']
        }
        logger.info(f"Phát pi_prediction_result đến phòng server: {prediction_data}")
        socketio.emit('pi_prediction_result', prediction_data, room='server')

        # Ghi log thành công
        processing_time = time.time() - start_time
        logger.info(f"Xử lý upload thành công cho client {client_id} trong {processing_time:.3f} giây")
        
        response = jsonify({'status': 'OK'})
        response.headers['X-Processing-Time'] = processing_time
        return response, 200

    except Exception as e:
        logger.error(f"Lỗi xử lý upload: {str(e)}")
        return jsonify({'error': 'Lỗi server nội bộ'}), 500

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=PORT, debug=True)