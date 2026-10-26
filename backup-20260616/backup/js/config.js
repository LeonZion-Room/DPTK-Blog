const CardConfig = {
  basicInfo: {
    name: '谢达',
    title: '深圳市龙岗区坂田街道办事处',
    title2: '党工委副书记、办事处主任',
    phone: '18922878666',
    email: 'szxieda@163.com',
    logo: 'https://img.cdn1.vip/i/69a0748ac1626_1772123274.png',
    company: '深圳市龙岗区坂田街道办事处',
    address: ''
  },
  
  sections: [
    { type: 'title', level: 1, title: '个人简介' },
    { 
      type: 'grid', 
      images: [
        { src: 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', jump: 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg' },
        { src: 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', jump: 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg' },
        { src: 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', jump: 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg' },
        { src: 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', jump: 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg' }
      ]
    },
    { type: 'title', level: 2, title: '工作经历' },
    { type: 'video', src: 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.mp4', poster: 'https://img.naixiai.cn/2026/02/26/knxdpq99c1rmy0cw87hsmbk95g_result_.fr.jpeg' },
    { type: 'title', level: 3, title: '教育背景' },
    { type: 'image', src: 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp', jump: 'https://img.cdn1.vip/i/69a0725acaea9_1772122714.webp' }
  ],

  wechat: {
    appId: '',
    timestamp: '',
    nonceStr: '',
    signature: '',
    shareTitle: '',
    shareDesc: '',
    shareLink: '',
    shareImgUrl: ''
  },

  settings: {
    showCallConfirm: true,
    defaultSaveOptions: {
      title: true,
      email: true,
      company: false,
      address: false
    }
  }
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = CardConfig;
}
