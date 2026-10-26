const http = require('http');
const url = require('url');
const WechatSignService = require('./wechat-sign');

WechatSignService.init('YOUR_APP_ID', 'YOUR_APP_SECRET');

const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  if (parsedUrl.pathname === '/api/wechat-sign') {
    const pageUrl = parsedUrl.query.url;
    
    if (!pageUrl) {
      res.statusCode = 400;
      res.end(JSON.stringify({ error: '缺少url参数' }));
      return;
    }
    
    try {
      const signData = await WechatSignService.generateSignature(pageUrl);
      res.end(JSON.stringify(signData));
    } catch (error) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: error.message }));
    }
  } else {
    res.statusCode = 404;
    res.end(JSON.stringify({ error: 'Not found' }));
  }
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`签名服务运行在端口 ${PORT}`);
});
