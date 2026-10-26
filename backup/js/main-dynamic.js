(function() {
  'use strict';

  const DynamicConfig = {
    config: null,
    serverUrl: '',
    currentNotice: null,

    // 辅助函数：将相对URL或本地IP URL转换为使用serverUrl的绝对URL
    getAbsoluteUrl(url) {
      if (!url) return url;
      if (url.startsWith('http')) {
        // 检查是否是本地IP URL，如果是则替换为serverUrl
        if (url.includes('172.168.') || url.includes('192.168.') || url.includes('127.0.0.1') || url.includes('localhost')) {
          // 提取路径部分
          const path = url.replace(/^https?:\/\/[^\/]+/, '');
          return this.serverUrl + path;
        }
        return url;
      }
      if (url.startsWith('/')) {
        return this.serverUrl + url;
      } else {
        return this.serverUrl + '/' + url;
      }
    },

    async init() {
      await this.loadConfig();
      this.renderBasicInfo();
      this.renderSections();
      await this.initWechatShare();
      this.bindEvents();
      this.checkAutoPopupNotice();
    },

    async loadConfig() {
      try {
        // 先使用默认域名获取配置
        const defaultServerUrl = window.location.origin;
        
        // 获取URL中的页面参数
        const urlParams = new URLSearchParams(window.location.search);
        const pageId = urlParams.get('page');
        
        const url = pageId ? 
          defaultServerUrl + '/api/card-config?page=' + pageId : 
          defaultServerUrl + '/api/card-config';
        
        const response = await fetch(url);
        if (response.ok) {
          this.config = await response.json();
          // 使用currentPage的sections
          if (this.config.currentPage) {
            this.config.sections = this.config.currentPage.sections;
          }
          // 设置serverUrl为后端返回的currentDomain
          if (this.config.currentDomain) {
            this.serverUrl = this.config.currentDomain;
          } else {
            this.serverUrl = defaultServerUrl;
          }
        } else {
          this.config = typeof CardConfig !== 'undefined' ? CardConfig : this.getDefaultConfig();
          this.serverUrl = defaultServerUrl;
        }
      } catch (e) {
        this.config = typeof CardConfig !== 'undefined' ? CardConfig : this.getDefaultConfig();
        this.serverUrl = window.location.origin;
      }
    },

    getDefaultConfig() {
      return {
        basicInfo: {
          name: '姓名',
          title: '职位',
          title2: '',
          phone: '电话',
          email: '',
          logo: ''
        },
        sections: [],
        settings: {
          showCallConfirm: true
        }
      };
    },

    renderBasicInfo() {
      // 移除之前的主题类
      document.body.className = document.body.className.replace(/bg-theme-\S+/g, '').trim();
      document.body.className = document.body.className.replace(/content-theme-\S+/g, '').trim();
      
      // 检查是否有名片信息组件
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      
      if (contactSection) {
        // 使用名片信息组件的数据
        const info = contactSection;
        
        // 应用背景主题
        const bgTheme = info.bgTheme || info.theme || 'theme-purple-pink';
        const bgClass = 'bg-' + bgTheme;
        document.body.classList.add(bgClass);
        
        // 应用内容主题
        const contentTheme = info.contentTheme || info.theme || 'theme-purple-pink';
        const contentClass = 'content-' + contentTheme;
        document.body.classList.add(contentClass);
        
        document.getElementById('name').textContent = info.name || '';
        document.getElementById('phone').textContent = info.phone || '';
        document.getElementById('title').textContent = info.title || '';
        document.getElementById('title2').textContent = info.title2 || '';
        document.getElementById('email').textContent = info.email ? '邮箱：' + info.email : '';
        
        const logoEl = document.getElementById('logo');
        if (logoEl && info.logo) {
          logoEl.src = this.getAbsoluteUrl(info.logo);
        }
        
        document.title = info.name ? info.name + '的微信名片' : '微信名片';
        
        // 显示名片信息部分
        const infoCardWrapper = document.querySelector('.info-card-wrapper');
        if (infoCardWrapper) {
          infoCardWrapper.style.display = 'block';
        }
      } else {
        // 没有名片信息组件，使用默认主题并隐藏名片信息部分
        document.body.classList.add('bg-theme-purple-pink');
        document.body.classList.add('content-theme-purple-pink');
        const infoCardWrapper = document.querySelector('.info-card-wrapper');
        if (infoCardWrapper) {
          infoCardWrapper.style.display = 'none';
        }
        document.title = '微信名片';
      }
    },

    renderSections() {
      const container = document.getElementById('contentSections');
      if (!container || !this.config.sections) return;
      
      let html = '';
      
      // 获取名片信息中的logo
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const logoUrl = contactSection ? contactSection.logo : '';
      
      this.config.sections.forEach((section, index) => {
        // 跳过名片信息组件，因为已经在renderBasicInfo中处理
        if (section.type === 'contact') {
          return;
        }
        
        switch (section.type) {
          case 'title':
            html += this.renderTitleSection(section, logoUrl);
            break;
          case 'image':
            html += '<div class="image-card" data-jump="' + (this.getAbsoluteUrl(section.jump) || '') + '">' +
                    '<img src="' + this.getAbsoluteUrl(section.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; max-height: 100%; object-fit: contain;">' +
                    '</div>';
            break;
          case 'video':
            const videoId = 'video_' + Date.now() + Math.floor(Math.random() * 1000);
            html += '<div class="video-card">' +
                    '<video id="' + videoId + '" src="' + this.getAbsoluteUrl(section.src) + '" poster="' + (this.getAbsoluteUrl(section.poster) || '') + '" controls playsinline webkit-playsinline></video>' +
                    '</div>';
            break;
          case 'grid':
            html += '<div class="image-grid">';
            section.images.forEach((img) => {
              html += '<div class="image-grid-item" data-jump="' + (this.getAbsoluteUrl(img.jump) || '') + '">' +
                      '<img src="' + this.getAbsoluteUrl(img.src) + '" alt="" loading="lazy">' +
                      '</div>';
            });
            html += '</div>';
            break;
          case 'carousel':
            html += this.renderCarouselSection(section);
            break;
          case 'tabs':
            html += this.renderTabsSection(section);
            break;
          case 'notice':
            html += this.renderNoticeCard(section);
            break;
        }
      });
      
      container.innerHTML = html;
      
      // 处理视频封面
      this.setupVideoCovers();
    },

    renderNoticeCard(section) {
      let html = '<div class="notice-card" onclick="DynamicConfig.showNoticePopup()">';
      html += '<div class="notice-header">';
      html += '<div class="notice-icon">📢</div>';
      html += '<div class="notice-title">' + (section.title || '公告') + '</div>';
      html += '</div>';
      html += '<div class="notice-content">' + (section.content || '') + '</div>';
      if (section.tag) {
        html += '<div class="notice-footer">';
        html += '<span class="notice-tag">' + section.tag + '</span>';
        html += '</div>';
      }
      html += '</div>';
      return html;
    },

    checkAutoPopupNotice() {
      if (!this.config.sections) return;
      
      const autoPopupNotice = this.config.sections.find(
        section => section.type === 'notice' && section.autoPopup
      );
      
      if (autoPopupNotice) {
        this.currentNotice = autoPopupNotice;
        setTimeout(() => {
          this.showNoticePopup();
        }, 500);
      }
    },

    showNoticePopup() {
      const notice = this.currentNotice || this.config.sections.find(section => section.type === 'notice');
      if (!notice) return;
      
      this.currentNotice = notice;
      
      document.getElementById('noticePopupTitle').textContent = notice.title || '公告';
      document.getElementById('noticePopupBody').textContent = notice.content || '';
      
      const footer = document.getElementById('noticePopupFooter');
      footer.innerHTML = '';
      if (notice.tag) {
        footer.innerHTML = '<span class="notice-tag">' + notice.tag + '</span>';
      }
      
      document.getElementById('noticePopup').classList.add('show');
    },

    hideNoticePopup() {
      document.getElementById('noticePopup').classList.remove('show');
    },

    renderTitleSection(section, logoUrl) {
      const level = section.level || 1;
      const color = section.color || '';
      const titleLogo = section.logo || logoUrl;
      const colorStyle = color ? 'style="background: ' + color + '; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;"' : '';
      const decoStyle = color ? 'style="background: linear-gradient(90deg, ' + color + ', transparent);"' : '';
      const decoStyle2 = color ? 'style="background: linear-gradient(90deg, transparent, ' + color + ', transparent);"' : '';
      const decoStyle3 = color ? 'style="background: linear-gradient(180deg, ' + color + ', ' + color + ');"' : '';
      
      if (level === 1) {
        // 一级标题：居中、加粗、装饰线
        let html = '<div class="section-title level-1">';
        html += '<span class="title-text" ' + colorStyle + '>' + section.title + '</span>';
        html += '</div>';
        return html;
      } else if (level === 2) {
        // 二级标题：居左、右侧带logo
        let html = '<div class="section-title level-2">';
        html += '<span class="title-text" ' + colorStyle + '>' + section.title + '</span>';
        if (titleLogo) {
          html += '<img class="title-logo" src="' + this.getAbsoluteUrl(titleLogo) + '" alt="Logo">';
        }
        html += '</div>';
        return html;
      } else if (level === 3) {
        // 三级标题：居左、左侧带logo
        let html = '<div class="section-title level-3">';
        html += '<span class="title-text" ' + colorStyle + '>' + section.title + '</span>';
        html += '</div>';
        return html;
      }
    },
    
    renderCarouselSection(section) {
      const carouselId = 'carousel_' + Date.now() + Math.floor(Math.random() * 1000);
      const autoplay = section.autoplay || false;
      const interval = section.interval || 3000;
      
      let html = '<div class="carousel" id="' + carouselId + '">';
      html += '<div class="carousel-container">';
      
      section.items.forEach((item, index) => {
        html += '<div class="carousel-item" data-jump="' + (this.getAbsoluteUrl(item.jump) || '') + '">';
        html += '<img src="' + this.getAbsoluteUrl(item.src) + '" alt="' + (item.title || '') + '" loading="lazy">';
        if (item.title) {
          html += '<div class="carousel-item-title">' + item.title + '</div>';
        }
        html += '</div>';
      });
      
      html += '</div>';
      html += '<div class="carousel-indicators"></div>';
      html += '<button class="carousel-prev">&lt;</button>';
      html += '<button class="carousel-next">&gt;</button>';
      html += '</div>';
      
      // 添加轮播图初始化脚本，确保DOM完全渲染
      setTimeout(() => {
        this.initCarousel(carouselId, autoplay, interval);
      }, 100);
      
      return html;
    },
    
    initCarousel(carouselId, autoplay, interval) {
      const carousel = document.getElementById(carouselId);
      if (!carousel) return;
      
      const container = carousel.querySelector('.carousel-container');
      const items = carousel.querySelectorAll('.carousel-item');
      const indicators = carousel.querySelector('.carousel-indicators');
      const prevBtn = carousel.querySelector('.carousel-prev');
      const nextBtn = carousel.querySelector('.carousel-next');
      
      if (items.length === 0) return;
      
      let currentIndex = 0;
      // 确保轮播容器和项目的宽度正确设置
      const carouselWidth = carousel.offsetWidth;
      container.style.width = (carouselWidth * items.length) + 'px';
      items.forEach(item => {
        item.style.width = carouselWidth + 'px';
        item.style.minWidth = carouselWidth + 'px';
        item.style.flexShrink = '0';
      });
      const itemWidth = carouselWidth;
      
      // 创建指示器
      items.forEach((item, index) => {
        const indicator = document.createElement('button');
        indicator.classList.add('carousel-indicator');
        if (index === 0) indicator.classList.add('active');
        indicator.addEventListener('click', () => {
          goToSlide(index);
        });
        indicators.appendChild(indicator);
      });
      
      // 轮播函数
      function goToSlide(index) {
        currentIndex = index;
        container.style.transform = `translateX(-${currentIndex * itemWidth}px)`;
        
        // 更新指示器状态
        const indicatorButtons = indicators.querySelectorAll('.carousel-indicator');
        indicatorButtons.forEach((btn, i) => {
          if (i === currentIndex) {
            btn.classList.add('active');
          } else {
            btn.classList.remove('active');
          }
        });
      }
      
      // 上一张
      prevBtn.addEventListener('click', () => {
        currentIndex = (currentIndex - 1 + items.length) % items.length;
        goToSlide(currentIndex);
      });
      
      // 下一张
      nextBtn.addEventListener('click', () => {
        currentIndex = (currentIndex + 1) % items.length;
        goToSlide(currentIndex);
      });
      
      // 自动播放
      if (autoplay) {
        let autoplayInterval = setInterval(() => {
          currentIndex = (currentIndex + 1) % items.length;
          goToSlide(currentIndex);
        }, interval);
        
        // 鼠标悬停时暂停自动播放
        carousel.addEventListener('mouseenter', () => {
          clearInterval(autoplayInterval);
        });
        
        carousel.addEventListener('mouseleave', () => {
          autoplayInterval = setInterval(() => {
            currentIndex = (currentIndex + 1) % items.length;
            goToSlide(currentIndex);
          }, interval);
        });
      }
      
      // 处理跳转
      items.forEach(item => {
        item.addEventListener('click', () => {
          const jumpUrl = item.dataset.jump;
          if (jumpUrl) {
            const isWechat = navigator.userAgent.toLowerCase().includes('micromessenger');
            if (isWechat) {
              try {
                window.location.href = jumpUrl;
              } catch (e) {
                const link = document.createElement('a');
                link.href = jumpUrl;
                link.target = '_blank';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }
            } else {
              window.open(jumpUrl, '_blank');
            }
          }
        });
      });
    },
    
    renderTabsSection(section) {
      const tabsId = 'tabs_' + Date.now() + Math.floor(Math.random() * 1000);
      
      let html = '<div class="tabs" id="' + tabsId + '">';
      html += '<div class="tabs-header">';
      
      section.tabs.forEach((tab, index) => {
        html += '<div class="tab-item' + (index === 0 ? ' active' : '') + '" data-index="' + index + '">';
        html += tab.title;
        html += '</div>';
      });
      
      html += '</div>';
      html += '<div class="tabs-content">';
      
      section.tabs.forEach((tab, index) => {
        html += '<div class="tab-pane' + (index === 0 ? ' active' : '') + '" data-index="' + index + '">';
        
        // 渲染tab内的区块
        tab.sections.forEach((tabSection) => {
          switch (tabSection.type) {
            case 'title':
              html += this.renderTitleSection(tabSection, '');
              break;
            case 'image':
              html += '<div class="image-card" data-jump="' + (this.getAbsoluteUrl(tabSection.jump) || '') + '">' +
                      '<img src="' + this.getAbsoluteUrl(tabSection.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; max-height: 100%; object-fit: contain;">' +
                      '</div>';
              break;
            case 'video':
              const videoId = 'video_' + Date.now() + Math.floor(Math.random() * 1000);
              html += '<div class="video-card">' +
                      '<video id="' + videoId + '" src="' + this.getAbsoluteUrl(tabSection.src) + '" poster="' + (this.getAbsoluteUrl(tabSection.poster) || '') + '" controls playsinline webkit-playsinline></video>' +
                      '</div>';
              break;
            case 'grid':
              html += '<div class="image-grid">';
              tabSection.images.forEach((img) => {
                html += '<div class="image-grid-item" data-jump="' + (this.getAbsoluteUrl(img.jump) || '') + '">' +
                        '<img src="' + this.getAbsoluteUrl(img.src) + '" alt="" loading="lazy">' +
                        '</div>';
              });
              html += '</div>';
              break;
          }
        });
        
        html += '</div>';
      });
      
      html += '</div>';
      html += '</div>';
      
      // 添加tabs初始化脚本
      setTimeout(() => {
        this.initTabs(tabsId);
      }, 0);
      
      return html;
    },
    
    initTabs(tabsId) {
      const tabs = document.getElementById(tabsId);
      if (!tabs) return;
      
      const tabItems = tabs.querySelectorAll('.tab-item');
      const tabPanes = tabs.querySelectorAll('.tab-pane');
      
      tabItems.forEach((item, index) => {
        item.addEventListener('click', () => {
          // 移除所有active类
          tabItems.forEach(i => i.classList.remove('active'));
          tabPanes.forEach(p => p.classList.remove('active'));
          
          // 添加active类到当前项
          item.classList.add('active');
          tabPanes[index].classList.add('active');
        });
      });
    },
    
    setupVideoCovers() {
      const videos = document.querySelectorAll('video');
      videos.forEach((video) => {
        // 如果没有设置poster，自动生成第一帧作为封面
        if (!video.poster) {
          video.addEventListener('loadeddata', () => {
            this.generateVideoThumbnail(video);
          });
          
          // 尝试加载视频数据以触发loadeddata事件
          video.load();
        }
      });
    },
    
    generateVideoThumbnail(video) {
      try {
        // 创建一个canvas元素
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 320;
        canvas.height = video.videoHeight || 180;
        
        // 绘制视频的第一帧
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // 将canvas转换为base64图片
        const thumbnailUrl = canvas.toDataURL('image/jpeg');
        
        // 设置视频的poster属性
        video.poster = thumbnailUrl;
      } catch (e) {
        console.error('生成视频封面失败:', e);
      }
    },

    async initWechatShare() {
      console.log('开始初始化微信分享...');
      
      // 优先从名片信息组件获取数据
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      let info = contactSection || this.config.basicInfo;
      
      // 使用当前页面的分享标题、描述和图标
      let shareTitle = '';
      let shareDesc = '';
      let shareIcon = '';
      
      if (this.config.currentPage) {
        shareTitle = this.config.currentPage.share_title || '';
        shareDesc = this.config.currentPage.share_desc || '';
        shareIcon = this.config.currentPage.share_icon || '';
      }
      
      // 如果没有配置分享信息，则使用名片信息
      if (!shareTitle) {
        shareTitle = (info.name || '微信名片') + '的微信名片';
      }
      
      if (!shareDesc) {
        shareDesc = (info.title || '') + (info.phone ? ' | ' + info.phone : '');
      }
      
      if (!shareIcon) {
        shareIcon = info.logo || '';
      }
      
      // 确保分享图片是完整的URL
      let finalShareIcon = shareIcon;
      if (finalShareIcon && !finalShareIcon.startsWith('http')) {
        if (finalShareIcon.startsWith('/')) {
          finalShareIcon = this.serverUrl + finalShareIcon;
        } else {
          finalShareIcon = this.serverUrl + '/' + finalShareIcon;
        }
      }
      if (!finalShareIcon) {
        finalShareIcon = this.serverUrl + '/uploads/20260415_063127_e659038a.png';
      }
      
      console.log('分享设置:', {
        title: shareTitle,
        desc: shareDesc,
        link: window.location.href,
        imgUrl: finalShareIcon
      });
      
      console.log('是否微信环境:', WechatJSSDK.isWechat());
      
      if (!WechatJSSDK.isWechat()) {
        console.log('非微信环境，跳过JSSDK配置');
        return;
      }
      
      console.log('开始获取微信签名...');
      
      try {
        const signUrl = this.serverUrl + '/api/wechat-sign?url=' + encodeURIComponent(window.location.href.split('#')[0]);
        console.log('签名请求URL:', signUrl);
        
        const response = await fetch(signUrl);
        const signData = await response.json();
        
        console.log('微信签名数据:', signData);
        
        if (signData.appId) {
          console.log('开始配置微信JSSDK...');
          WechatJSSDK.config({
            appId: signData.appId,
            timestamp: signData.timestamp,
            nonceStr: signData.nonceStr,
            signature: signData.signature,
            onReady: () => {
              console.log('微信JSSDK ready，设置分享数据');
              WechatJSSDK.setShareData({
                title: shareTitle,
                desc: shareDesc,
                link: window.location.href,
                imgUrl: finalShareIcon
              });
            },
            onError: (res) => {
              console.error('微信JSSDK配置错误:', res);
              // 不显示错误提示，保持用户体验
            }
          });
        } else {
          console.error('签名数据中没有appId');
        }
      } catch (e) {
        console.error('获取微信签名失败:', e);
        // 不显示错误提示，保持用户体验
      }
    },

    bindEvents() {
      const btnCopy = document.getElementById('btnCopy');
      if (btnCopy) {
        btnCopy.addEventListener('click', () => this.handleCopy());
      }
      
      const btnCall = document.getElementById('btnCall');
      if (btnCall) {
        btnCall.addEventListener('click', () => this.handleCall());
      }
      
      // 公告弹窗事件
      const closeNoticeBtn = document.getElementById('closeNoticePopup');
      if (closeNoticeBtn) {
        closeNoticeBtn.addEventListener('click', () => this.hideNoticePopup());
      }
      
      const noticePopup = document.getElementById('noticePopup');
      if (noticePopup) {
        noticePopup.addEventListener('click', (e) => {
          if (e.target.id === 'noticePopup') this.hideNoticePopup();
        });
      }
      

      
      const cancelCall = document.getElementById('cancelCall');
      if (cancelCall) {
        cancelCall.addEventListener('click', () => this.hideCallConfirm());
      }
      
      const confirmCall = document.getElementById('confirmCall');
      if (confirmCall) {
        confirmCall.addEventListener('click', () => this.doCall());
      }
      
      const callConfirm = document.getElementById('callConfirm');
      if (callConfirm) {
        callConfirm.addEventListener('click', (e) => {
          if (e.target.id === 'callConfirm') this.hideCallConfirm();
        });
      }
      

      
      const contentSections = document.getElementById('contentSections');
      if (contentSections) {
        contentSections.addEventListener('click', (e) => {
          const card = e.target.closest('.image-card, .image-grid-item');
          if (card && card.dataset.jump) {
            const jumpUrl = card.dataset.jump;
            
            // 检测是否在微信环境中
            const isWechat = navigator.userAgent.toLowerCase().includes('micromessenger');
            
            if (isWechat) {
              // 在微信环境中，尝试使用不同的跳转方式
              try {
                // 方法1：直接设置location.href
                window.location.href = jumpUrl;
              } catch (e) {
                // 方法2：创建一个a标签并点击
                const link = document.createElement('a');
                link.href = jumpUrl;
                link.target = '_blank';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }
            } else {
              // 在非微信环境中，使用window.open
              window.open(jumpUrl, '_blank');
            }
          }
        });
      }
    },





    handleCopy() {
      console.log('点击了复制信息按钮');
      if (navigator.vibrate) navigator.vibrate(50);
      
      // 优先使用名片信息组件的数据
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const info = contactSection || this.config.basicInfo;
      
      // 构建要复制的文本
      let copyText = '';
      
      if (info.name) {
        copyText += `姓名：${info.name}\n`;
      }
      if (info.phone) {
        copyText += `电话：${info.phone}\n`;
      }
      if (info.title2 || info.title) {
        copyText += `职位：${info.title2 || info.title}\n`;
      }
      if (info.email) {
        copyText += `邮箱：${info.email}\n`;
      }
      if (info.company) {
        copyText += `公司：${info.company}\n`;
      }
      if (info.address) {
        copyText += `地址：${info.address}\n`;
      }
      
      // 尝试复制到剪贴板
      this.copyToClipboard(copyText);
    },

    copyToClipboard(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        // 使用现代的Clipboard API
        navigator.clipboard.writeText(text).then(() => {
          this.showToast('信息已复制到剪贴板', 'success');
        }).catch(() => {
          this.fallbackCopy(text);
        });
      } else {
        // 使用传统的方法作为后备
        this.fallbackCopy(text);
      }
    },

    fallbackCopy(text) {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      textArea.style.top = '-9999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        document.execCommand('copy');
        this.showToast('信息已复制到剪贴板', 'success');
      } catch (e) {
        this.showToast('复制失败，请手动复制', 'error');
      }
      
      document.body.removeChild(textArea);
    },

    handleCall() {
      if (navigator.vibrate) navigator.vibrate(50);
      if (this.config.settings && this.config.settings.showCallConfirm) {
        this.showCallConfirm();
      } else {
        this.doCall();
      }
    },

    showCallConfirm() {
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const phone = contactSection ? contactSection.phone : this.config.basicInfo.phone;
      document.getElementById('confirmPhone').textContent = phone;
      document.getElementById('callConfirm').classList.add('show');
    },

    hideCallConfirm() {
      document.getElementById('callConfirm').classList.remove('show');
    },

    doCall() {
      this.hideCallConfirm();
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const phone = contactSection ? contactSection.phone : this.config.basicInfo.phone;
      window.location.href = 'tel:' + phone;
    },

    showToast(message, type, duration) {
      const toast = document.getElementById('toast');
      toast.textContent = message;
      toast.className = 'toast show' + (type ? ' ' + type : '');
      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.className = 'toast', 300);
      }, duration || 2000);
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => DynamicConfig.init());
  } else {
    DynamicConfig.init();
  }

  window.DynamicConfig = DynamicConfig;
})();
