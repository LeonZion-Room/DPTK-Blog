(function() {
  'use strict';

  const Utils = {
    showToast: function(message, type, duration) {
      const toast = document.getElementById('toast');
      if (!toast) return;
      
      toast.textContent = message;
      toast.className = 'toast show';
      if (type) {
        toast.classList.add(type);
      }
      
      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
          toast.className = 'toast';
        }, 300);
      }, duration || 2000);
    },

    vibrate: function() {
      if (navigator.vibrate) {
        navigator.vibrate(50);
      }
    },

    isWechat: function() {
      return WechatJSSDK.isWechat();
    },

    isIOS: function() {
      return /iPad|iPhone|iPod/.test(navigator.userAgent);
    },

    isAndroid: function() {
      return /Android/.test(navigator.userAgent);
    }
  };

  const CardApp = {
    config: null,
    
    init: function() {
      this.config = typeof CardConfig !== 'undefined' ? CardConfig : null;
      
      if (!this.config) {
        console.error('配置文件未加载');
        return;
      }
      
      this.renderBasicInfo();
      this.renderSections();
      this.initWechatShare();
      this.bindEvents();
    },

    renderBasicInfo: function() {
      const info = this.config.basicInfo;
      
      document.getElementById('name').textContent = info.name || '';
      document.getElementById('phone').textContent = info.phone || '';
      document.getElementById('title').textContent = info.title || '';
      document.getElementById('title2').textContent = info.title2 || '';
      document.getElementById('email').textContent = info.email ? '邮箱：' + info.email : '';
      
      const logoEl = document.getElementById('logo');
      if (logoEl && info.logo) {
        logoEl.src = info.logo;
      }
      
      document.title = info.name ? info.name + '的微信名片' : '微信名片';
      
      const metaDesc = document.querySelector('meta[name="description"]');
      if (metaDesc) {
        metaDesc.content = (info.name || '') + ' - ' + (info.title || '') + ' ' + (info.phone || '');
      }
    },

    renderSections: function() {
      const container = document.getElementById('contentSections');
      if (!container || !this.config.sections) return;
      
      let html = '';
      
      this.config.sections.forEach((section) => {
        switch (section.type) {
          case 'title':
            html += '<div class="section-title level-' + (section.level || 1) + '">' + section.title + '</div>';
            break;
            
          case 'image':
            html += '<div class="image-card" data-jump="' + (section.jump || '') + '">' +
                    '<img src="' + section.src + '" alt="" loading="lazy">' +
                    '</div>';
            break;
            
          case 'video':
            html += '<div class="video-card">' +
                    '<video src="' + section.src + '" poster="' + (section.poster || '') + '" controls playsinline webkit-playsinline></video>' +
                    '</div>';
            break;
            
          case 'grid':
            html += '<div class="image-grid">';
            section.images.forEach((img) => {
              html += '<div class="image-grid-item" data-jump="' + (img.jump || '') + '">' +
                      '<img src="' + img.src + '" alt="" loading="lazy">' +
                      '</div>';
            });
            html += '</div>';
            break;
        }
      });
      
      container.innerHTML = html;
    },

    initWechatShare: function() {
      const info = this.config.basicInfo;
      const wechatConfig = this.config.wechat;
      
      if (!Utils.isWechat()) {
        return;
      }
      
      const shareTitle = wechatConfig.shareTitle || (info.name + '的微信名片');
      const shareDesc = wechatConfig.shareDesc || (info.title + ' | ' + info.phone);
      const shareLink = wechatConfig.shareLink || window.location.href;
      const shareImgUrl = wechatConfig.shareImgUrl || info.logo || '';
      
      if (wechatConfig.appId && wechatConfig.timestamp && wechatConfig.signature) {
        WechatJSSDK.config({
          appId: wechatConfig.appId,
          timestamp: wechatConfig.timestamp,
          nonceStr: wechatConfig.nonceStr,
          signature: wechatConfig.signature,
          onReady: () => {
            WechatJSSDK.setShareData({
              title: shareTitle,
              desc: shareDesc,
              link: shareLink,
              imgUrl: shareImgUrl
            });
          }
        });
      } else {
        if (wx && wx.ready) {
          wx.ready(() => {
            WechatJSSDK.setShareData({
              title: shareTitle,
              desc: shareDesc,
              link: shareLink,
              imgUrl: shareImgUrl
            });
          });
        }
      }
    },

    bindEvents: function() {
      document.getElementById('btnShare').addEventListener('click', () => {
        this.handleShare();
      });
      
      document.getElementById('btnSave').addEventListener('click', () => {
        this.handleSave();
      });
      
      document.getElementById('btnCall').addEventListener('click', () => {
        this.handleCall();
      });
      
      document.getElementById('closeShareGuide').addEventListener('click', () => {
        WechatJSSDK.hideShareGuide();
      });
      
      document.getElementById('shareGuide').addEventListener('click', (e) => {
        if (e.target.id === 'shareGuide') {
          WechatJSSDK.hideShareGuide();
        }
      });
      
      document.getElementById('cancelCall').addEventListener('click', () => {
        this.hideCallConfirm();
      });
      
      document.getElementById('confirmCall').addEventListener('click', () => {
        this.doCall();
      });
      
      document.getElementById('callConfirm').addEventListener('click', (e) => {
        if (e.target.id === 'callConfirm') {
          this.hideCallConfirm();
        }
      });
      
      document.getElementById('cancelSave').addEventListener('click', () => {
        this.hideSaveOptions();
      });
      
      document.getElementById('confirmSave').addEventListener('click', () => {
        this.doSave();
      });
      
      document.getElementById('saveOptions').addEventListener('click', (e) => {
        if (e.target.id === 'saveOptions') {
          this.hideSaveOptions();
        }
      });
      
      document.getElementById('contentSections').addEventListener('click', (e) => {
        const card = e.target.closest('.image-card, .image-grid-item');
        if (card) {
          const jump = card.dataset.jump;
          if (jump) {
            this.showImageViewer(jump);
          }
        }
      });
    },

    handleShare: function() {
      Utils.vibrate();
      
      if (Utils.isWechat()) {
        WechatJSSDK.showShareGuide();
      } else if (navigator.share) {
        const info = this.config.basicInfo;
        navigator.share({
          title: info.name + '的微信名片',
          text: info.title + ' | ' + info.phone,
          url: window.location.href
        }).catch(() => {});
      } else {
        Utils.showToast('请在微信中打开以使用分享功能', 'error');
      }
    },

    handleSave: function() {
      Utils.vibrate();
      this.showSaveOptions();
    },

    showSaveOptions: function() {
      const saveOptions = document.getElementById('saveOptions');
      if (saveOptions) {
        saveOptions.classList.add('show');
      }
    },

    hideSaveOptions: function() {
      const saveOptions = document.getElementById('saveOptions');
      if (saveOptions) {
        saveOptions.classList.remove('show');
      }
    },

    doSave: function() {
      const info = this.config.basicInfo;
      const includeTitle = document.getElementById('optTitle').checked;
      const includeEmail = document.getElementById('optEmail').checked;
      const includeCompany = document.getElementById('optCompany').checked;
      const includeAddress = document.getElementById('optAddress').checked;
      
      const vcardData = {
        firstName: info.name,
        mobile: info.phone
      };
      
      if (includeTitle) {
        vcardData.title = info.title2 || info.title;
      }
      
      if (includeEmail) {
        vcardData.email = info.email;
      }
      
      if (includeCompany) {
        vcardData.organization = info.company;
      }
      
      if (includeAddress) {
        vcardData.address = info.address;
      }
      
      this.hideSaveOptions();
      
      try {
        VCardGenerator.saveToContact(vcardData);
        Utils.showToast('正在保存到通讯录...', 'success');
      } catch (e) {
        Utils.showToast('保存失败，请手动添加', 'error');
      }
    },

    handleCall: function() {
      Utils.vibrate();
      
      if (this.config.settings && this.config.settings.showCallConfirm) {
        this.showCallConfirm();
      } else {
        this.doCall();
      }
    },

    showCallConfirm: function() {
      const callConfirm = document.getElementById('callConfirm');
      const confirmPhone = document.getElementById('confirmPhone');
      
      if (callConfirm && confirmPhone) {
        confirmPhone.textContent = this.config.basicInfo.phone;
        callConfirm.classList.add('show');
      }
    },

    hideCallConfirm: function() {
      const callConfirm = document.getElementById('callConfirm');
      if (callConfirm) {
        callConfirm.classList.remove('show');
      }
    },

    doCall: function() {
      this.hideCallConfirm();
      
      const phone = this.config.basicInfo.phone;
      if (phone) {
        window.location.href = 'tel:' + phone;
      }
    },

    showImageViewer: function(src) {
      let viewer = document.getElementById('imageViewer');
      
      if (!viewer) {
        viewer = document.createElement('div');
        viewer.id = 'imageViewer';
        viewer.className = 'image-viewer';
        viewer.innerHTML = '<span class="image-viewer-close"></span><img src="" alt="">';
        document.body.appendChild(viewer);
        
        viewer.addEventListener('click', (e) => {
          if (e.target === viewer || e.target.classList.contains('image-viewer-close')) {
            this.hideImageViewer();
          }
        });
      }
      
      const img = viewer.querySelector('img');
      if (img) {
        img.src = src;
      }
      
      viewer.classList.add('show');
    },

    hideImageViewer: function() {
      const viewer = document.getElementById('imageViewer');
      if (viewer) {
        viewer.classList.remove('show');
      }
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      CardApp.init();
    });
  } else {
    CardApp.init();
  }

  window.CardApp = CardApp;
})();
