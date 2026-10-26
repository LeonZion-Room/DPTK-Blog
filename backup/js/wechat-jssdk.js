const WechatJSSDK = {
  isWechat: function() {
    const ua = navigator.userAgent.toLowerCase();
    return ua.indexOf('micromessenger') !== -1;
  },

  isReady: false,

  config: function(options) {
    console.log('WechatJSSDK.config 被调用');
    console.log('是否微信环境:', this.isWechat());
    
    if (!this.isWechat()) {
      console.log('非微信环境，不配置JSSDK');
      return;
    }

    const defaultOptions = {
      debug: false,
      appId: '',
      timestamp: '',
      nonceStr: '',
      signature: '',
      jsApiList: [
        'updateAppMessageShareData',
        'updateTimelineShareData',
        'onMenuShareAppMessage',
        'onMenuShareTimeline'
      ]
    };

    const config = Object.assign({}, defaultOptions, options);
    
    console.log('微信JSSDK配置参数:', {
      appId: config.appId,
      timestamp: config.timestamp,
      nonceStr: config.nonceStr,
      signature: config.signature ? config.signature.substring(0, 20) + '...' : ''
    });

    wx.config({
      debug: config.debug,
      appId: config.appId,
      timestamp: config.timestamp,
      nonceStr: config.nonceStr,
      signature: config.signature,
      jsApiList: config.jsApiList
    });

    wx.ready(() => {
      this.isReady = true;
      console.log('微信JSSDK配置成功 (wx.ready)');
      
      if (config.onReady) {
        config.onReady();
      }
    });

    wx.error((res) => {
      console.error('微信JSSDK配置失败 (wx.error):', res);
      
      if (config.onError) {
        config.onError(res);
      }
    });
  },

  setShareData: function(data) {
    if (!this.isWechat()) {
      console.log('非微信环境，不设置分享数据');
      return;
    }

    console.log('设置分享数据:', data);

    const shareData = {
      title: data.title || document.title,
      desc: data.desc || '',
      link: data.link || window.location.href,
      imgUrl: data.imgUrl || '',
      success: function() {
        console.log('分享成功');
        if (data.success) {
          data.success();
        }
      },
      cancel: function() {
        console.log('分享取消');
        if (data.cancel) {
          data.cancel();
        }
      }
    };

    console.log('最终分享数据:', shareData);

    // 只有当JSSDK准备就绪时才调用微信API方法
    if (this.isReady) {
      if (wx.updateAppMessageShareData) {
        console.log('使用 updateAppMessageShareData');
        wx.updateAppMessageShareData(shareData);
      }

      if (wx.updateTimelineShareData) {
        console.log('使用 updateTimelineShareData');
        wx.updateTimelineShareData({
          title: shareData.title,
          link: shareData.link,
          imgUrl: shareData.imgUrl,
          success: shareData.success,
          cancel: shareData.cancel
        });
      }

      if (wx.onMenuShareAppMessage) {
        console.log('使用 onMenuShareAppMessage');
        wx.onMenuShareAppMessage(shareData);
      }

      if (wx.onMenuShareTimeline) {
        console.log('使用 onMenuShareTimeline');
        wx.onMenuShareTimeline({
          title: shareData.title,
          link: shareData.link,
          imgUrl: shareData.imgUrl,
          success: shareData.success,
          cancel: shareData.cancel
        });
      }
    } else {
      console.log('JSSDK未准备就绪，跳过分享设置');
    }
  },

  showShareGuide: function() {
    console.log('showShareGuide 被调用');
    console.log('是否微信环境:', this.isWechat());
    console.log('User Agent:', navigator.userAgent);
    
    // 无论是否在微信环境，都先尝试显示分享引导
    const shareGuide = document.getElementById('shareGuide');
    console.log('shareGuide 元素:', shareGuide);
    
    if (shareGuide) {
      console.log('添加 show 类到 shareGuide');
      shareGuide.classList.remove('show'); // 先移除再添加，确保触发重绘
      setTimeout(() => {
        shareGuide.classList.add('show');
        console.log('show 类已添加，当前类列表:', shareGuide.className);
      }, 10);
    } else {
      console.error('找不到 shareGuide 元素！');
      // 如果找不到元素，尝试使用其他方式
      alert('请点击右上角「...」分享给好友');
    }
  },

  hideShareGuide: function() {
    const shareGuide = document.getElementById('shareGuide');
    if (shareGuide) {
      shareGuide.classList.remove('show');
    }
  }
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = WechatJSSDK;
}
