var SignalStrengthChart = function(ylabel, title, key, div_id, labels_div) {
  this.title = title;
  this.ylabel = ylabel;
  this.key = key;
  this.element = div_id;
  this.labels_div = labels_div;
  this.signalStrengths = [];
  this.listOfDevices = new deviceList();
  this.g = null; /* The actual graph, initialized by
   initializeDygraph so that the chart doesn't have
   data until data is retrieved from the server. */
  var dStart = new Date();
  this.curTime = dStart.getTime();
  this.initialized = false;
  return this;
};

/** Initializes a dygraph.
*/
SignalStrengthChart.prototype.initializeDygraph = function() {
  this.g = new Dygraph(document.getElementById(this.element),
   // For possible data formats, see http://dygraphs.com/data.html
   // The x-values could also be dates, e.g. '2012/03/15'
   this.signalStrengths,
   {
       // options go here. See http://dygraphs.com/options.html
       legend: 'always',
       animatedZooms: true,
       title: this.title,
       /* labels initialized with mac addr because host names may not be
       immediately available */
       labels: ['time'].concat(Object.keys(this.listOfDevices.devices)),
       labelsDiv: this.labels_div,
       xlabel: 'Time',
       ylabel: this.ylabel,
       axisLabelFontSize: 12
   });
};

/** Adds a point on the graph (with a time and an object that maps
  MAC addresses with signal strengths).
 * @param {int} time - we need time for the x axis of the dygraph, in seconds
 * @param {Object} sig_point - MAC addresses and signal strengths mapping
*/
SignalStrengthChart.prototype.addPoint = function(time, sig_point) {
  var numNewKeys = Object.keys(sig_point).length;
  console.log('num new keys ' + numNewKeys);
  var pointToAdd = [time];
  for (var mac_addr_index in Object.keys(sig_point)) {
    var mac_addr = (Object.keys(sig_point))[mac_addr_index];
    var index = this.listOfDevices.get(mac_addr);
    console.log('mac_addr=' + mac_addr + ' --> index=' + index);
    pointToAdd[index + 1] = sig_point[mac_addr];
    console.log(sig_point[mac_addr]);
  }

  if (this.signalStrengths.length > 0 &&
    pointToAdd.length > this.signalStrengths[0].length) {
    while (this.signalStrengths[0].length < pointToAdd.length) {
      for (var point = 0; point < this.signalStrengths.length; point++) {
        this.signalStrengths[point].push(null);
      }
    }
    if (this.initialized) {
      this.initializeDygraph();
    }
  }
  this.signalStrengths.push(pointToAdd);
  console.log(this.signalStrengths);
};

/** Gets data from JSON page and updates dygraph.
 * @param {boolean} is_moca - if graph displays moca devices
*/
SignalStrengthChart.prototype.getData = function(is_moca) {
  var self = this;
  if (!is_moca) {
    $.getJSON('/signal.json', function(signal_data) {
      var time = new Date();
      self.addPoint(time, signal_data[self.key]);
    });
  }
  if (is_moca) {
    $.getJSON('/moca.json', function(moca_data) {
      var time = new Date();
      self.addPoint(time, moca_data[self.key]);
      showData('#bitloading', moca_data['moca_bitloading'], 'Bitloading');
      showData('#nbas2', moca_data['moca_nbas'], 'NBAS (from moca2)');
      showBitloading(moca_data['moca_bitloading']);
    });
  }
  $.getJSON('/content.json?checksum=42', function(data) {
    var time = new Date();
    var host_names = self.listOfDevices.hostNames(data['host_names'], is_moca);
    var host_names_array = [];
    for (var mac_addr in host_names) {
      host_names_array.push(host_names[mac_addr]);
    }
    if (!self.initialized) {
      if (self.signalStrengths.length == 0) {
        self.addPoint(time, {});
      }
      self.initializeDygraph();
      self.initialized = true;
    }
    else {
      self.g.updateOptions({file: self.signalStrengths,
        labels: ['time'].concat(host_names_array)
        });
    }
    showData('#host_names', data['host_names'], 'Host Name');
    $('#softversion').html($('<div/>').text(data['softversion']).html());
  });
  setTimeout(function() {
    self.getData(is_moca);
  }, 1000);
};

function showData(div, data, dataName) {
  var nameString = '';
  for (var mac_addr in data) {
    if (data[mac_addr] != '') {
      nameString += '<p> MAC Address: ' +
       $('<div/>').text(mac_addr).html() + ', ' + dataName + ': ' +
       $('<div/>').text(data[mac_addr]).html() + '</p>';
    }
    else {
      nameString += '<p> MAC Address: ' +
       $('<div/>').text(mac_addr).html() + '</p>';
    }
  }
  $(div).html(nameString);
}

function showBitloading(data) {
  var prefix = '$BRCM2$';
  $('#bit_table').html('');
  $('#nbas').html('');
  var nbas_dict = {};
  for (var mac_addr in data) {
    var nbas = 0;
    var bitloading = data[mac_addr];
    for (var i = prefix.length; i < bitloading.length; i++) {
      var bl = parseInt(bitloading[i], 16)
      if (isNaN(bl)) {
        console.log('Could not parse', bitloading[i], 'as a number.');
        continue;
      }
      nbas += bl;
      if (bl < 5) {
        $('#bit_table').append('<span class="bit" ' +
        'style="background-color:#FF4136">' + bitloading[i] + '</span>');
      }
      else if (bl < 7) {
        $('#bit_table').append('<span class="bit" ' +
        'style="background-color:#FFDC00">' + bitloading[i] + '</span>');
      }
      else {
        $('#bit_table').append('<span class="bit" ' +
        'style="background-color:#2ECC40">' + bitloading[i] + '</span>');
      }
    }
    $('#bit_table').append('<br style="clear:both"><br>');
    nbas_dict[mac_addr] = nbas;
  }
  for (var mac_addr in nbas_dict) {
    $('#nbas').append(mac_addr + ' NBAS: ' + nbas_dict[mac_addr] + '<br>');
  }
  $('#nbas').append('<br>');
}
