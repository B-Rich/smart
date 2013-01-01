/*
 * Copyright 2011-2012 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define*/

define([
	"dojo/_base/array",
	"umc/tools",
	"umc/i18n!umc/modules/uvmm"
], function(array, tools, _) {
	var self = {
		dict2list: function(dict) {
			var list = [];
			tools.forIn(dict, function(ikey, ival) {
				list.push({
					id: ikey,
					label: ival
				});
			});
			return list;
		},
		architecture: [
			{ id: 'i686', label: '32 bit' },
			{ id: 'x86_64', label: '64 bit' }
		],
		bootDevices: [
			{ id: 'hd', label: _('Hard drive') },
			{ id: 'cdrom', label: _( 'CDROM drive' ) },
			{ id: 'network', label: _( 'Network' ) }
		],
		rtcOffset: [
			{ id: 'utc', label: _('Coordinated Universal Time'), vt: ['kvm-hvm', 'xen-xen'] },
			{ id: 'localtime', label: _('Local time zone'), vt: ['kvm-hvm', 'xen-xen'] },
			{ id: 'variable', label: _('Guest controlled'), vt: ['kvm-hvm', 'xen-hvm'] }
		],
		getRtcOffset: function(domain_type, rtc_offset) {
			return array.filter(self.rtcOffset, function(irtc) {
				return array.indexOf(irtc.vt, domain_type) >= 0 || irtc.id == rtc_offset;
			});
		},
		domainStates: {
			RUNNING : _( 'running' ),
			SHUTOFF : _( 'shut off' ),
			PAUSED : _( 'paused' ),
			IDLE : _( 'running (idle)' ),
			CRASHED : _( 'shut off (crashed)' )
		},
		getDomainStateDescription: function( domain ) {
			var text = self.domainStates[ domain.state ];
			if ( true === domain.suspended ) {
				text += ' ' + _( '(saved state)' );
			}
			return text;
		},
		parseStorageSize: function(size) {
			var pattern = /^([0-9]+(?:[,.][0-9]+)?)[ \t]*(?:([KkMmGgTtPp])(?:[Ii]?[Bb])?|[Bb])?$/;
			var match = pattern.exec(size);
			if (match === null) {
				return null;
			}
			var mem = parseFloat(match[1].replace(',', '.'));
			var unit = match[2];
			switch (unit) {
				case 'P': case 'p':
					mem *= 1024;
				case 'T': case 't':
					mem *= 1024;
				case 'G': case 'g':
					mem *= 1024;
				case 'M': case 'm':
					mem *= 1024;
				case 'K': case 'k':
					mem *= 1024;
			}
			return mem;
		},
		virtualizationTechnology: [
			{ id: 'kvm-hvm', label: _( 'Full virtualization (KVM)' ) },
			{ id: 'xen-hvm', label: _( 'Full virtualization (XEN)' ) },
			{ id: 'xen-xen', label: _( 'Paravirtualization (XEN)' ) }
		],
		getVirtualizationTechnology: function(options) {
			// return all technologies that are supported by the corresponding
			// opertating system type (KVM/Xen)
			return array.filter(self.virtualizationTechnology, function(itech) {
				return itech.id.indexOf(options.domain_type) === 0;
			});
		},
		keyboardLayout: [
			{ id: 'ar', label: _('Arabic') },
			{ id: 'da', label: _('Danish') },
			{ id: 'de', label: _('German') },
			{ id: 'de-ch', label: _('German-Switzerland') },
			{ id: 'en-gb', label: _('English-Britain') },
			{ id: 'en-us', label: _('English-America') },
			{ id: 'es', label: _('Spanish') },
			{ id: 'et', label: _('Estonian') },
			{ id: 'fi', label: _('Finnish') },
			{ id: 'fo', label: _('Faroese') },
			{ id: 'fr', label: _('French') },
			{ id: 'fr-be', label: _('French-Belgium') },
			{ id: 'fr-ca', label: _('French-Canada') },
			{ id: 'fr-ch', label: _('French-Switzerland') },
			{ id: 'hr', label: _('Croatian') },
			{ id: 'hu', label: _('Hungarian') },
			{ id: 'is', label: _('Icelandic') },
			{ id: 'it', label: _('Italian') },
			{ id: 'ja', label: _('Japanese') },
			{ id: 'lt', label: _('Lithuanian') },
			{ id: 'lv', label: _('Latvian') },
			{ id: 'mk', label: _('Macedonian') },
			{ id: 'nl', label: _('Dutch') },
			{ id: 'nl-be', label: _('Dutch-Belgium') },
			{ id: 'no', label: _('Norwegian') },
			{ id: 'pl', label: _('Polish') },
			{ id: 'pt', label: _('Portuguese') },
			{ id: 'pt-br', label: _('Portuguese-Brasil') },
			{ id: 'ru', label: _('Russian') },
			{ id: 'sl', label: _('Slovene') },
			{ id: 'sv', label: _('Swedish') },
			{ id: 'th', label: _('Thai') },
			{ id: 'tr', label: _('Turkish') }
		],
		getCPUs: function(options) {
			// query the domain's node and get its number of CPUs
			var nodeURI = options.nodeURI || options.domainURI.split('#')[0];
			return tools.umcpCommand('uvmm/node/query', {
				nodePattern: nodeURI
			}).then(function(data) {
				// query successful
				var list = [ { id: 1, label: '1' } ];
				if (data.result.length) {
					// we got a result
					var nCPU = data.result[0].cpus;
					for (var i = 2; i <= nCPU; ++i) {
						list.push({ id: i, label: '' + i });
					}
				}
				return list;
			}, function() {
				// fallback
				return [ { id: 1, label: '1' } ];
			});
		},
		interfaceModels: {
			'rtl8139': _( 'Default (RealTek RTL-8139)' ),
			'e1000': _( 'Intel PRO/1000' ),
			'netfront': _( 'Paravirtual device (xen)' ),
			'virtio': _( 'Paravirtual device (virtio)' )
		},
		getInterfaceModels: function(options) {
			var list = [];
			tools.forIn(self.interfaceModels, function(ikey, ilabel) {
				if (ikey == 'virtio') {
					if (options.domain_type == 'kvm') {
						list.push({ id: ikey, label: ilabel });
					}
				}
				else if (ikey == 'netfront') {
					if (options.domain_type == 'xen') {
						list.push({ id: ikey, label: ilabel });
					}
				}
				else {
					list.push({ id: ikey, label: ilabel });
				}
			});
			return list;
		},
		getDefaultInterfaceModel: function(/*String*/ domain_type, /*Boolean*/ paravirtual) {
			if (paravirtual && domain_type == 'xen') {
				return 'netfront';
			}
			if (paravirtual && domain_type == 'kvm') {
				return 'virtio';
			}
			return 'rtl8139';
		},
		interfaceTypes: [
			{ id: 'bridge', label: _( 'Bridge' ) },
			{ id: 'network:default', label: _( 'NAT' ) }
		],
		blockDevices: {
			'cdrom': _( 'CD/DVD-ROM drive' ),
			'disk': _( 'Hard drive' ),
			'floppy': _( 'Floppy drive' )
		},
		blockDevicePath: {
			disk: '/dev/',
			cdrom: '/dev/cdrom',
			floppy: '/dev/fd0'
		},
		diskChoice: [
			{ id: 'new', label: _('Create a new image') },
			{ id: 'exists', label: _('Choose existing image') },
			{ id: 'block', label: _('Use a local device') },
			{ id: 'empty', label: _('No media') }
		],
		driverCache: {
			'default': _('Hypervisor default'),
			'none': _('No host caching, no forced sync (none)'),
			'writethrough': _('Read caching, forced sync (write-through)'),
			'writeback': _('Read/write caching, no forced sync (write-back)'),
			'directsync': _('No host caching, forced sync (direct-sync)'),
			'unsafe': _('Read/write caching, sync filtered out (unsafe)'),
		},
		getPools: function(options) {
			if (!options.nodeURI) {
				return [];
			}
			return tools.umcpCommand('uvmm/storage/pool/query', {
				nodeURI: options.nodeURI
			}).then(function(data) {
				return array.map(data.result, function(iitem) {
					return iitem.name;
				});
			}, function() {
				// fallback
				return [];
			});
		},
		getVolumes: function(options) {
			if (!options.nodeURI || !options.pool) {
				return [];
			}
			return tools.umcpCommand('uvmm/storage/volume/query', {
				nodeURI: options.nodeURI,
				pool: options.pool,
				type: options.type || null
			}).then(function(data) {
				return array.map(data.result, function(iitem) {
					return {
						id: iitem.volumeFilename,
						type: iitem.driver_type,
						label: iitem.volumeFilename
					};
				});
			}, function() {
				// fallback
				return [];
			});
		},
		getImageFormat: function(options) {
			ISO = {id: 'iso', label: _('ISO format (iso)')};
			RAW = {id: 'raw', label: _('Simple format (raw)')};
			QCOW2 = {id: 'qcow2', label: _('Extended format (qcow2)'), preselected: true};
			var list = [];
			if (options.type == 'cdrom') {
				list.push(ISO);
			} else if (options.type == 'floppy') {
				list.push(RAW);
			} else {
				list.push(RAW);
				if (options.domain_type == 'kvm') {
					// add qcow2 as pre-selected item
					list.push(QCOW2);
				}
			}
			return list;
		},
		getNodes: function() {
			return tools.umcpCommand('uvmm/query', {
				type: 'node',
				nodePattern: '*'
			}).then(function(data) {
				return array.filter( data.result, function( node ) {
					return node.available;
				} );
			});
		},
		getProfiles: function(options) {
			return tools.umcpCommand('uvmm/profile/query', {
				nodeURI: options.nodeURI
			}).then(function(data) {
				return data.result;
			});
		},
		getNodeType: function( uri ) {
			var colon = uri.indexOf( ':' );
			if ( colon == -1 ) {
				return null;
			}
			return uri.slice( 0, colon );
		}
	};
	return self;
});
