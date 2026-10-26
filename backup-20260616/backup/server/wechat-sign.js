const crypto = require('crypto');

const WechatSignService = {
  appId: '',
  appSecret: '',
  accessToken: null,
  accessTokenExpire: 0,
  jsapiTicket: null,
  jsapiTicketExpire: 0,

  init(appId, appSecret) {
    this.appId = appId;
    this.appSecret = appSecret;
  },

  async getAccessToken() {
    if (this.accessToken && Date.now() < this.accessTokenExpire) {
      return this.accessToken;
    }

    const url = `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=${this.appId}&secret=${this.appSecret}`;
    const response = await fetch(url);
    const data = await response.json();
    
    if (data.access_token) {
      this.accessToken = data.access_token;
      this.accessTokenExpire = Date.now() + (data.expires_in - 300) * 1000;
      return this.accessToken;
    }
    
    throw new Error(data.errmsg || '获取access_token失败');
  },

  async getJsapiTicket() {
    if (this.jsapiTicket && Date.now() < this.jsapiTicketExpire) {
      return this.jsapiTicket;
    }

    const accessToken = await this.getAccessToken();
    const url = `https://api.weixin.qq.com/cgi-bin/ticket/getticket?access_token=${accessToken}&type=jsapi`;
    const response = await fetch(url);
    const data = await response.json();
    
    if (data.ticket) {
      this.jsapiTicket = data.ticket;
      this.jsapiTicketExpire = Date.now() + (data.expires_in - 300) * 1000;
      return this.jsapiTicket;
    }
    
    throw new Error(data.errmsg || '获取jsapi_ticket失败');
  },

  generateNonceStr() {
    return Math.random().toString(36).substr(2, 15);
  },

  generateTimestamp() {
    return Math.floor(Date.now() / 1000);
  },

  async generateSignature(url) {
    const ticket = await this.getJsapiTicket();
    const nonceStr = this.generateNonceStr();
    const timestamp = this.generateTimestamp();

    const string1 = `jsapi_ticket=${ticket}&noncestr=${nonceStr}&timestamp=${timestamp}&url=${url}`;
    const signature = crypto.createHash('sha1').update(string1).digest('hex');

    return {
      appId: this.appId,
      timestamp: timestamp,
      nonceStr: nonceStr,
      signature: signature
    };
  }
};

module.exports = WechatSignService;
