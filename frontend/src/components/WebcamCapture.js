import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import io from 'socket.io-client';

function WebcamCapture() {
  const NGROK_URL = "https://0fdf-171-250-162-44.ngrok-free.app".trim();
  const videoRef = useRef(null);
  const [predictionResult, setPredictionResult] = useState({ result: '', score: 0 });
  const [webcamError, setWebcamError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isVideoConnected, setIsVideoConnected] = useState(false);
  const [frameIntervalTime, setFrameIntervalTime] = useState(500);
  const navigate = useNavigate();
  const userEmail = localStorage.getItem('userEmail') || `user_${Date.now()}@example.com`; // Giá trị mặc định với timestamp
  const socket = useRef(null);
  const peerConnection = useRef(null);
  const frameInterval = useRef(null);
  const lastFrameResult = useRef({ result: '', score: 0 });

  useEffect(() => {
    console.log('userEmail:', userEmail);
    if (!userEmail || userEmail.trim() === '') {
      alert('Email không hợp lệ. Vui lòng quay lại trang đầu và nhập email!');
      navigate('/');
      return;
    }

    socket.current = io(NGROK_URL);

    socket.current.on('connect', () => {
      console.log('Socket.IO đã kết nối từ client:', socket.current.id);
      setupWebRTC();
    });

    socket.current.on('connect_error', (error) => {
      console.error('Lỗi kết nối Socket.IO:', error.message);
      setWebcamError('Kết nối tới server thất bại: ' + error.message);
    });

    const setupWebRTC = async () => {
      console.log('Bắt đầu setupWebRTC');
      let stream;
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('Trình duyệt không hỗ trợ getUserMedia');
        }

        console.log('Đang yêu cầu truy cập webcam...');
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 320 },
            height: { ideal: 240 },
            frameRate: { ideal: 15 }
          }
        });
        console.log('Đã truy cập webcam thành công, stream:', stream);

        if (!videoRef.current) {
          throw new Error('videoRef không tồn tại, không thể gán stream');
        }

        videoRef.current.srcObject = stream;
        console.log('Stream đã được gán vào videoRef');

        videoRef.current.onloadedmetadata = () => {
          console.log('Video metadata tải xong, kích thước:', videoRef.current.videoWidth, 'x', videoRef.current.videoHeight);
          setIsSending(true);
        };

        videoRef.current.onerror = (e) => {
          console.error('Lỗi video element:', e);
          setWebcamError('Lỗi video element: ' + e.message);
        };

        peerConnection.current = new RTCPeerConnection({
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' },
            { urls: 'stun:stun3.l.google.com:19302' },
            { urls: 'stun:stun4.l.google.com:19302' },
            { urls: 'stun:stun.services.mozilla.com' },
            { urls: 'stun:stun.nextcloud.com:443' },
            { urls: 'turn:turn.anyfirewall.com:443?transport=tcp', username: 'webrtc', credential: 'webrtc' },
            { urls: 'turn:global.turn.twilio.com:3478?transport=udp', username: 'user', credential: 'pass' },
            { urls: 'turn:global.turn.twilio.com:443?transport=tcp', username: 'user', credential: 'pass' }
          ],
          iceTransportPolicy: 'all',
          iceCandidatePoolSize: 30,
          bundlePolicy: 'max-bundle',
          rtcpMuxPolicy: 'require'
        });

        stream.getTracks().forEach(track => {
          console.log('Thêm track vào peerConnection:', track.kind);
          peerConnection.current.addTrack(track, stream);
        });

        peerConnection.current.onicecandidate = (event) => {
          if (event.candidate && peerConnection.current.remoteDescription) {
            socket.current.emit('ice-candidate', { clientId: socket.current.id, candidate: event.candidate });
            console.log('Đã gửi ICE candidate:', event.candidate);
          }
        };

        let retryCount = 0;
        const maxRetries = 3;

        peerConnection.current.oniceconnectionstatechange = () => {
          const state = peerConnection.current.iceConnectionState;
          console.log('Trạng thái ICE:', state);
          if (state === 'failed') {
            console.log('Kết nối WebRTC thất bại, thử lại...');
            retryConnection();
          } else if (state === 'disconnected') {
            console.log('Mất kết nối WebRTC, thử lại...');
            setFrameIntervalTime(1000);
            retryConnection();
          } else if (state === 'connected') {
            console.log('Kết nối WebRTC thành công!');
            setIsVideoConnected(true);
            setFrameIntervalTime(500);
          }
        };

        const retryConnection = async () => {
          if (retryCount >= maxRetries) {
            setWebcamError('Không thể kết nối WebRTC sau nhiều lần thử lại.');
            console.log(`Đã thử lại ${maxRetries} lần, không thể kết nối WebRTC`);
            // Thông báo cho server để xóa container
            socket.current.emit('client-disconnected', { clientId: socket.current.id, email: userEmail });
            socket.current.disconnect(); // Ngắt kết nối socket
            return;
          }

          retryCount++;
          console.log(`Thử lại kết nối WebRTC lần ${retryCount}`);

          try {
            peerConnection.current.close();
            const newPeerConnection = new RTCPeerConnection({
              iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' },
                { urls: 'stun:stun3.l.google.com:19302' },
                { urls: 'stun:stun4.l.google.com:19302' },
                { urls: 'stun:stun.services.mozilla.com' },
                { urls: 'stun:stun.nextcloud.com:443' },
                { urls: 'turn:turn.anyfirewall.com:443?transport=tcp', username: 'webrtc', credential: 'webrtc' },
                { urls: 'turn:global.turn.twilio.com:3478?transport=udp', username: 'user', credential: 'pass' },
                { urls: 'turn:global.turn.twilio.com:443?transport=tcp', username: 'user', credential: 'pass' }
              ],
              iceTransportPolicy: 'all',
              iceCandidatePoolSize: 30,
              bundlePolicy: 'max-bundle',
              rtcpMuxPolicy: 'require'
            });

            peerConnection.current = newPeerConnection;
            stream.getTracks().forEach(track => newPeerConnection.addTrack(track, stream));
            newPeerConnection.onicecandidate = peerConnection.current.onicecandidate;
            newPeerConnection.oniceconnectionstatechange = peerConnection.current.oniceconnectionstatechange;
            newPeerConnection.onicegatheringstatechange = peerConnection.current.onicegatheringstatechange;

            const offer = await newPeerConnection.createOffer();
            await newPeerConnection.setLocalDescription(offer);
            socket.current.emit('offer', { clientId: socket.current.id, offer: newPeerConnection.localDescription, email: userEmail });
            console.log('Đã gửi offer mới:', newPeerConnection.localDescription);
          } catch (error) {
            console.error('Lỗi khi thử lại kết nối WebRTC:', error);
            setWebcamError('Lỗi thử lại kết nối WebRTC: ' + error.message);
          }
        };

        peerConnection.current.onicegatheringstatechange = () => {
          console.log('Trạng thái ICE gathering:', peerConnection.current.iceGatheringState);
        };

        const offer = await peerConnection.current.createOffer();
        await peerConnection.current.setLocalDescription(offer);
        socket.current.emit('offer', { clientId: socket.current.id, offer: peerConnection.current.localDescription, email: userEmail });
        console.log('Đã gửi offer với email:', userEmail);
      } catch (error) {
        console.error('Lỗi truy cập webcam:', error);
        if (error.name === 'NotAllowedError') {
          setWebcamError('Quyền truy cập webcam bị từ chối. Vui lòng cấp quyền trong trình duyệt.');
        } else if (error.name === 'NotReadableError') {
          setWebcamError('Không thể truy cập webcam: Thiết bị đang được sử dụng bởi ứng dụng khác.');
        } else if (error.name === 'NotFoundError') {
          setWebcamError('Không tìm thấy webcam trên thiết bị.');
        } else {
          setWebcamError('Không thể truy cập webcam: ' + error.message);
        }
      }
    };

    socket.current.on('answer', async (data) => {
      try {
        await peerConnection.current.setRemoteDescription(new RTCSessionDescription(data.answer));
        console.log('Remote description đã được thiết lập');
      } catch (error) {
        console.error('Lỗi thiết lập remote description:', error);
        setWebcamError('Lỗi thiết lập kết nối WebRTC: ' + error.message);
      }
    });

    socket.current.on('ice-candidate', async (data) => {
      try {
        if (data.candidate && peerConnection.current.remoteDescription) {
          await peerConnection.current.addIceCandidate(new RTCIceCandidate(data.candidate));
          console.log('Đã thêm ICE candidate:', data.candidate);
        }
      } catch (error) {
        console.error('Lỗi thêm ICE candidate:', error);
        setWebcamError('Lỗi thêm ICE candidate: ' + error.message);
      }
    });

    socket.current.on('prediction_result', (data) => {
      console.log('Nhận prediction_result:', data);
      if (data.error) {
        console.error('Lỗi từ server:', data.error);
        setWebcamError('Lỗi từ server: ' + data.error);
        setIsProcessing(false);
        return;
      }
      setPredictionResult({
        result: data.result,
        score: data.score || 0,
      });
      lastFrameResult.current = { result: data.result, score: data.score };
      setIsProcessing(false);
    });

    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        videoRef.current.srcObject.getTracks().forEach(track => track.stop());
      }
      if (socket.current) {
        socket.current.emit('client-disconnected', { clientId: socket.current.id, email: userEmail });
        socket.current.disconnect();
      }
      if (peerConnection.current) {
        peerConnection.current.close();
      }
      if (frameInterval.current) {
        clearInterval(frameInterval.current);
      }
    };
  }, [navigate, userEmail]);

  useEffect(() => {
    console.log('isSending thay đổi:', isSending);
    if (!isSending) {
      if (frameInterval.current) {
        console.log('Hủy interval gửi khung hình');
        clearInterval(frameInterval.current);
        frameInterval.current = null;
      }
      return;
    }

    const sendFrameInterval = () => {
      console.log('Kiểm tra trạng thái gửi:', isSending);
      if (!isSending) {
        console.log('Dừng gửi khung hình');
        return;
      }

      if (!isVideoConnected) {
        console.log('Chưa kết nối video qua WebRTC, tạm dừng gửi frame để ưu tiên băng thông');
        return;
      }

      setIsProcessing(true);
      const video = videoRef.current;
      if (!video || video.readyState < 2) {
        console.error('Video không sẵn sàng');
        setWebcamError('Video không sẵn sàng');
        setIsProcessing(false);
        return;
      }

      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        console.error('Không thể lấy context của canvas');
        setWebcamError('Không thể lấy context của canvas');
        setIsProcessing(false);
        return;
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const frameData = canvas.toDataURL('image/jpeg', 0.3);
      console.log('Chuẩn bị gửi khung hình, kích thước dữ liệu:', frameData.length);

      if (frameData.startsWith('data:image/jpeg;base64,')) {
        socket.current.emit('webcam_frame', { frame: frameData, email: userEmail, clientId: socket.current.id });
        console.log('Đã gửi webcam_frame với email:', userEmail);
      } else {
        console.error('Định dạng khung hình không hợp lệ:', frameData.substring(0, 50));
        setIsProcessing(false);
      }
    };

    frameInterval.current = setInterval(sendFrameInterval, frameIntervalTime);
    sendFrameInterval();

    return () => {
      if (frameInterval.current) {
        clearInterval(frameInterval.current);
        frameInterval.current = null;
      }
    };
  }, [isSending, userEmail, isVideoConnected, frameIntervalTime]);

  const stopSending = () => {
    console.log('Nút "Dừng" được nhấn');
    setIsSending(false);
    setIsProcessing(false);

    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
    const lastFrame = canvas.toDataURL('image/jpeg', 0.3);
    socket.current.emit('stop', {
      clientId: socket.current.id,
      email: userEmail,
      frame: lastFrame,
      lastResult: lastFrameResult.current
    });

    if (lastFrameResult.current.result === 'fire') {
      console.log('Chuyển hướng đến /result');
      navigate('/result');
    } else if (lastFrameResult.current.result === 'no_fire') {
      console.log('Chuyển hướng đến /final');
      navigate('/final');
    } else {
      console.log('Không có kết quả để chuyển hướng');
    }
  };

  if (webcamError) {
    return (
      <div className="bg-purple-50 flex justify-center items-center min-h-screen">
        <div className="bg-white p-10 rounded-xl shadow-lg w-full max-w-2xl space-y-6">
          <h1 className="text-2xl font-bold text-center text-red-600">Lỗi</h1>
          <p className="text-center">{webcamError}</p>
          <p className="text-center text-gray-600">Vui lòng kiểm tra: đóng các ứng dụng/tab khác đang dùng webcam.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-purple-50 flex justify-center items-center min-h-screen">
      <div className="bg-white p-10 rounded-xl shadow-lg w-full max-w-3xl flex space-x-6">
        <div className="flex-1 space-y-6 relative">
          <h1 className="text-2xl font-bold text-center">Phân tích cháy qua webcam</h1>
          <div className="flex justify-center relative">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="rounded-lg border shadow max-w-full w-full h-auto"
            />
            {predictionResult.result && (
              <p
                className={`absolute top-2 left-2 text-lg font-bold ${
                  predictionResult.result === 'fire' ? 'text-red-600' : 'text-green-500'
                }`}
              >
                {predictionResult.result === 'fire'
                  ? `Fire: ${predictionResult.score.toFixed(2)}`
                  : `Non-Fire: ${predictionResult.score.toFixed(2)}`}
              </p>
            )}
          </div>
          <div className="text-center space-y-4">
            <button
              onClick={stopSending}
              className="w-1/2 bg-blue-500 text-white p-3 rounded-lg hover:bg-blue-600"
              disabled={!isSending}
            >
              Dừng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default WebcamCapture;