import express from 'express';

const app = express();
const port = 5000;

// 解析JSON请求体
app.use(express.json());

app.get('/v1/temp/raw', (req, res) => {
  const data = {
    acc: { 
      // time: new Date().toLocaleTimeString(), 
      x: (Math.random() * 2 - 1).toFixed(2), 
      y: (Math.random() * 2 - 1).toFixed(2), 
      z: (Math.random() * 2 - 1).toFixed(2) 
    },
    angle: { 
      // time: new Date().toLocaleTimeString(), 
      x: (Math.random() * 360).toFixed(2), 
      y: (Math.random() * 360).toFixed(2), 
      z: (Math.random() * 360).toFixed(2) 
    }
  };
  res.json(data);
  console.log('Sent raw data', data);
});


var __data = {
  pid: {
    pos: {
      p: 0.1,
      i: 0.1,
      d: 0.1,
    },
    vel: {
      p: 0.1,
      i: 0.1,
      d: 0.1,
    },
  },
  mode: "auto",
  th: {
    maxv: 12.1,
    minv: 10.1,
  },
  man: {
    pitch: 20,
    yaw: 30,
  },
};

app.post('/v1/setting', (req, res) => {
  __data = req.body;
  console.log('Received setting data:', __data);
  res.json({ message: 'setting data received' });
});

app.get('/v1/setting', (req, res) => {
  
  res.json(__data);
  console.log('Sent setting data', __data);
});

app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
});