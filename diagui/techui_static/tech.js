var SignalStrengthChart = function(ylabel, title, key, div_id,
                                   labels_div, is_moca) {
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
  this.initialized = false;
  this.is_moca = is_moca;
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
       axisLabelFontSize: 10
   });
};

/** Adds a point on the graph (with a time and an object that maps
  MAC addresses with signal strengths).
 * @param {Object} time - we need time (a date object) for the x axis
 * @param {Object} sig_point - MAC addresses and signal strengths mapping
*/
SignalStrengthChart.prototype.addPoint = function(time, sig_point) {
  var numNewKeys = Object.keys(sig_point).length;
  var pointToAdd = [time];
  for (var mac_addr_index in Object.keys(sig_point)) {
    var mac_addr = (Object.keys(sig_point))[mac_addr_index];
    var index = this.listOfDevices.get(mac_addr);
    pointToAdd[index + 1] = sig_point[mac_addr];
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
};

var checksum = 0;

function checkData(data) {
  keys = ['wifi_signal_strength', 'moca_signal_strength',
          'moca_corrected_codewords', 'moca_uncorrected_codewords',
          'moca_bitloading', 'moca_nbas', 'other_aps', 'self_signals',
          'host_names', 'ip_addr'];
  for (var index in keys) {
    key = keys[index];
    if (!(key in data)) {
      data[keys[index]] = {};
    }
  }
  if (!('checksum' in data)) {
    data['checksum'] = 0;
  }
  if (!('softversion' in data)) {
    data['softversion'] = '';
  }
}

/** Gets data from JSON page and updates dygraph.
 * @param {array} graph_array - graphs that need updates
*/
function getData(graph_array) {
  var payload = [];
  payload.push('checksum=' + encodeURIComponent(checksum));
  url = '/techui.json?' + payload.join('&');
  $.getJSON(url, function(data) {
    checkData(data);
    checksum = data['checksum'];
    for (var i = 0; i < graph_array.length; i++) {
      graph = graph_array[i];
      var time = new Date();
      graph.addPoint(time, data[graph.key]);
      var host_names = {};
      if (graph.is_moca) {
        host_names = graph.listOfDevices.mocaHostNames(data['host_names']);
      } else {
        host_names = graph.listOfDevices.hostNames(data['host_names']);
      }

      var host_names_array = [];
      for (var mac_addr in host_names) {
        host_names_array.push(host_names[mac_addr]);
      }
      if (!graph.initialized) {
        if (graph.signalStrengths.length == 0) {
          graph.addPoint(time, {});
        }
        graph.initializeDygraph();
        graph.initialized = true;
      }
      else {
        graph.g.updateOptions({file: graph.signalStrengths,
          labels: ['time'].concat(host_names_array)
          });
      }
    }
    showDeviceTable('#device_info', data['host_names'], data['ip_addr']);
    showBitloading(data);
    $('#softversion').html($('<div/>').text(data['softversion']).html());
    // Send another request when the request succeeds
    getData(graph_array);
  });
}

function showDeviceTable(div, host_names, ip_addr) {
  var infoString = ('<table><tr><td><b>MAC Address</b></td><td><b>Host Name' +
                    '</b></td><td><b>IP Address</b></td></tr>');
  for (var mac_addr in host_names) {
    infoString += '<tr><td>' + mac_addr + '</td>';
    if (host_names[mac_addr] != '') {
      infoString += '<td>' + host_names[mac_addr] + '</td>';
    }
    else {
      infoString += '<td></td>';
    }
    if (ip_addr[mac_addr] != '') {
      infoString += '<td>' + ip_addr[mac_addr] + '</td>';
    }
    else {
      infoString += '<td></td>';
    }
    infoString += '</tr>';
  }
  infoString += '</table>';
  $(div).html(infoString);
}

function showBitloading(data) {
  var bit_data = data['moca_bitloading'];
  var nbas = data['moca_nbas'];
  var prefix = '$BRCM2$';
  $('#bitloading').html('');
  for (var mac_addr in bit_data) {
    $('#bitloading').append('<span>Bitloading: ' + mac_addr + '</span><br>');
    $('#bitloading').append('<span>NBAS: ' + nbas[mac_addr] + '</span><br>');
    var bitloading = bit_data[mac_addr];
    for (var i = prefix.length; i < bitloading.length; i++) {
      var bl = parseInt(bitloading[i], 16);
      if (isNaN(bl)) {
        console.log('Could not parse', bitloading[i], 'as a number.');
        continue;
      }
      if (bl < 5) {
        $('#bitloading').append('<span class="bit" ' +
        'style="background-color:#FF4136">' + bitloading[i] + '</span>');
      }
      else if (bl < 7) {
        $('#bitloading').append('<span class="bit" ' +
        'style="background-color:#FFDC00">' + bitloading[i] + '</span>');
      }
      else {
        $('#bitloading').append('<span class="bit" ' +
        'style="background-color:#2ECC40">' + bitloading[i] + '</span>');
      }
    }
    $('#bitloading').append('<br style="clear:both"><br>');
  }
}
