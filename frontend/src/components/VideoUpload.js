import React from 'react';

function VideoUpload() {
  return (
    <div className="bg-green-50 flex justify-center items-center min-h-screen">
      <div className="bg-white p-10 rounded-xl shadow-lg w-full max-w-2xl space-y-6">
        <h1 className="text-2xl font-bold text-center">Tải video lên để phân tích cháy</h1>
        <p className="text-center text-red-600">
          Tính năng tải video hiện đang được phát triển. Vui lòng sử dụng ảnh hoặc webcam!
        </p>
      </div>
    </div>
  );
}

export default VideoUpload;