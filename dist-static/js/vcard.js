const VCardGenerator = {
  generate: function(data) {
    let vcard = 'BEGIN:VCARD\n';
    vcard += 'VERSION:3.0\n';
    vcard += 'N:' + (data.lastName || '') + ';' + (data.firstName || '') + ';;;\n';
    vcard += 'FN:' + (data.firstName || '') + (data.lastName ? ' ' + data.lastName : '') + '\n';
    
    if (data.mobile) {
      vcard += 'TEL;TYPE=CELL:' + data.mobile + '\n';
    }
    
    if (data.phone) {
      vcard += 'TEL;TYPE=WORK:' + data.phone + '\n';
    }
    
    if (data.email) {
      vcard += 'EMAIL;TYPE=INTERNET:' + data.email + '\n';
    }
    
    if (data.organization) {
      vcard += 'ORG:' + data.organization + '\n';
    }
    
    if (data.title) {
      vcard += 'TITLE:' + data.title + '\n';
    }
    
    if (data.address) {
      vcard += 'ADR;TYPE=WORK:;;' + data.address + ';;;;\n';
    }
    
    if (data.url) {
      vcard += 'URL:' + data.url + '\n';
    }
    
    if (data.note) {
      vcard += 'NOTE:' + data.note + '\n';
    }
    
    vcard += 'END:VCARD';
    
    return vcard;
  },

  download: function(data, filename) {
    const vcardContent = this.generate(data);
    const blob = new Blob([vcardContent], { type: 'text/vcard;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'contact.vcf';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  },

  getDataURL: function(data) {
    const vcardContent = this.generate(data);
    return 'data:text/vcard;charset=utf-8,' + encodeURIComponent(vcardContent);
  },

  saveToContact: function(data) {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    const isAndroid = /Android/.test(navigator.userAgent);
    const isWechat = /micromessenger/i.test(navigator.userAgent);
    const vcardContent = this.generate(data);
    const filename = (data.firstName || 'contact') + '.vcf';
    
    // 优先尝试在新窗口打开vCard文件，让系统处理
    try {
      const blob = new Blob([vcardContent], { type: 'text/x-vcard;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      
      // 尝试多种方式唤起通讯录
      if (isIOS) {
        // iOS: 直接打开URL
        window.location.href = url;
        setTimeout(() => {
          URL.revokeObjectURL(url);
        }, 3000);
        return true;
      } else if (isAndroid) {
        // Android: 尝试多种方式
        // 方式1: 使用a标签下载
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        // 方式2: 尝试直接打开
        setTimeout(() => {
          try {
            window.open(url, '_blank');
          } catch(e) {}
        }, 500);
        
        setTimeout(() => {
          URL.revokeObjectURL(url);
        }, 3000);
        return true;
      } else {
        // 其他环境
        this.download(data, filename);
        URL.revokeObjectURL(url);
        return true;
      }
    } catch (e) {
      console.error('保存到通讯录失败:', e);
      
      // 备用方案: 普通下载
      this.download(data, filename);
      return false;
    }
  }
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = VCardGenerator;
}
