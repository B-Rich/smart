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
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/Deferred",
	"dijit/Dialog",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/Grid",
	"umc/widgets/Form",
	"umc/widgets/Text",
	"umc/widgets/TextBox",
	"umc/widgets/CheckBox",
	"umc/widgets/ComboBox",
	"umc/widgets/Button",
	"umc/modules/uvmm/DriveWizard",
	"umc/modules/uvmm/types",
	"umc/i18n!umc/modules/uvmm"
], function(declare, lang, array, Deferred, Dialog, tools, dialog, Grid, Form, Text, TextBox, CheckBox, ComboBox, Button, DriveWizard, types, _) {

	return declare("umc.modules.uvmm.DriveGrid", [ Grid ], {
		moduleStore: null,

		domain: null,

		query: {},

		sortIndex: null,

		style: 'width: 100%; height: 200px;',

		constructor: function() {
			lang.mixin(this, {
				cacheRowWidgets: false,
				columns: [{
					name: 'device',
					label: _('Type'),
					formatter: lang.hitch(this, function(dev) {
						return types.blockDevices[dev] || _('unknown');
					})
				}, {
					name: 'volumeFilename',
					label: _('Image')
				}, {
					name: 'size',
					label: _('Size')
				}, {
					name: 'pool',
					label: _('Pool')
				}],
				actions: [{
					name: 'edit',
					label: _('Edit'),
					iconClass: 'umcIconEdit',
					isMultiAction: false,
					isStandardAction: true,
					callback: lang.hitch(this, '_editDrive'),
					canExecute: lang.hitch( this, function( item ) {
						// when creating an instance drives can not be edited
						return !this.disabled && undefined !== this.domain.domainURI;
					} )
				}, {
					name: 'change_medium',
					label: _('Change medium'),
					isMultiAction: false,
					isStandardAction: false,
					callback: lang.hitch(this, '_changeMedium'),
					canExecute: function( item ) {
						return item.device == 'cdrom' || item.device == 'floppy';
					}
				}, {
					name: 'delete',
					label: _('Delete'),
					isMultiAction: false,
					isStandardAction: true,
					iconClass: 'umcIconDelete',
					callback: lang.hitch(this, '_removeDrive'),
					canExecute: lang.hitch(this, function(item) {
						return !this.disabled;
					})
				}, {
					name: 'add',
					label: _('Add drive'),
					isMultiAction: false,
					isContextAction: false,
					iconClass: 'umcIconAdd',
					callback: lang.hitch(this, '_addDrive'),
					canExecute: lang.hitch(this, function(item) {
						return !this.disabled;
					})
				}]
			});
		},

		_setDisabledAttr: function(value) {
			if (this.domain.domain_type === 'kvm') {
				this.disabled = value;
				this._grid.update();

				// disable actions in toolbar
				array.forEach(this._toolbar.getChildren(), lang.hitch(this, function(widget) {
					if (widget instanceof Button) {
						widget.set('disabled', value);
					}
				}));
			} else {
				this.inherited(arguments);
			}
		},

		buildRendering: function() {
			this.inherited( arguments );

			// deactivate sorting
			this._grid.canSort = function( col ) {
				return false;
			};
		},

		_nextID: function() {
			var newID = this.moduleStore.data.length + 1;

			array.forEach( this.moduleStore.data, function( item ) {
				if ( item.$id$ >= newID ) {
					newID = item.$id$ + 1;
				}
			} );

			return newID;
		},

		_changeMedium: function( ids, items ) {
			var old_cdrom = items[ 0 ];
			var _dialog = null, wizard = null;

			var _cleanup = function() {
				_dialog.hide();
				_dialog.destroyRecursive();
				wizard.destroyRecursive();
			};

			var _finished = lang.hitch( this, function( values ) {
				_cleanup();
				if ( undefined !== old_cdrom.target_dev ) {
					values.target_dev = old_cdrom.target_dev;
				}
				if ( undefined !== old_cdrom.target_bus ) {
					values.target_bus = old_cdrom.target_bus;
				}
				this.moduleStore.put( lang.mixin( {
					$id$: ids[ 0 ]
				}, values ) );
				this.filter();
			} );

			wizard = new DriveWizard({
				style: 'width: 450px; height:450px;',
				domain: this.domain,
				onFinished: _finished,
				onCancel: _cleanup,
				driveType: old_cdrom.device
			});

			_dialog = new Dialog({
				title: _('Change medium'),
				content: wizard
			});
			_dialog.show();
		},

		_editDrive: function( ids, items ) {
			var disk = items[ 0 ];
			var id = ids[ 0 ];

			var intro_msg = _( 'All image files are stored in so-called storage pools. They can be stored in a local directory, an LVM partition or a share (e.g. using iSCSI, NFS or CIFS).' );
			var kvm_msg = _( 'Hard drive images can be administrated in two ways on KVM systems; by default images are saved in the <i>Extended format (qcow2)</i>. This format supports copy-on-write which means that changes do not overwrite the original version, but store new versions in different locations. The internal references of the file administration are then updated to allow both access to the original and the new version. This technique is a prerequisite for efficiently managing snapshots of virtual machines. Alternatively, you can also access a hard drive image in <i>Simple format (raw)</i>. Snapshots can only be created when using hard drive images in <i>Extended format</i>. Only the <i>Simple format</i> is available on Xen systems.' );
			var pv_msg = _( 'Paravirtualisation is a special variant of virtualisation in which the virtualised operating system is adapted to the underlying virtualisation technology. This improves the performance. Linux systems usually support paravirtualisation out of the box. For Windows systems additional support drivers need to be installed, see the <a href="http://wiki.univention.de/index.php?title=UVMM_Technische_Details">Univention wiki</a> for details (currently only available in German).' );

			var msg = '<p>' + intro_msg + '</p>';
			if ( types.getNodeType( this.domain.nodeURI ) == 'qemu' ) {
				msg += '<p>' + kvm_msg + '</p>';
			}
			msg = '<p>' + pv_msg + '</p>';

			var _dialog = null, form = null;

			var _cleanup = function() {
				_dialog.hide();
				_dialog.destroyRecursive();
				form.destroyRecursive();
			};

			var _saveDrive = lang.hitch(this, function() {
				var values = form.gatherFormValues();
				// reset target if setting paravirtual has changed
				if ( disk.paravirtual != values.paravirtual ) {
					disk.target_bus = null;
					disk.target_dev = null;
				}
				disk.paravirtual = values.paravirtual;
				disk.driver_cache = values.driver_cache;
				this.moduleStore.put( disk );
				_cleanup();
				this.filter();
			});

			form = new Form({
				widgets: [
				{
					type: Text,
					name: '__message',
					content: msg,
					label: ''
				}, {
					name: 'device',
					type: ComboBox,
					value: disk.device,
					disabled: true,
					staticValues: types.dict2list(types.blockDevices)
				}, {
					name: 'pool',
					type: ComboBox,
					label: _( 'Pool' ),
					description: _('Each image is located within a so called storage pool, which might be a local directory, a device, an LVM volume or any type of share (e.g. mounted via iSCSI, NFS or CIFS).'),
					dynamicOptions: lang.hitch( this, function( options ) {
						return {
							nodeURI: this.domain.nodeURI
						};
					} ),
					dynamicValues: types.getPools,
					disabled: true
				}, {
					name: 'volumeFilename',
					type: TextBox,
					value: disk.volumeFilename,
					label: _( 'Filename' ),
					disabled: true
				}, {
					type: CheckBox,
					name: 'paravirtual',
					value: disk.paravirtual === undefined ? false : disk.paravirtual,
					label: _( 'Paravirtual drive' )
				}, {
					name: 'driver_cache',
					type: ComboBox,
					value: disk.driver_cache || 'default',
					label: _('Caching'),
					description: _('Configure cache behaviour of host.'),
					staticValues: types.dict2list(types.driverCache)
				} ],
				buttons: [{
					name: 'submit',
					label: _('Save'),
					style: 'float: right;',
					callback: function() {
						_saveDrive();
					}
				}, {
					name: 'cancel',
					label: _('Cancel'),
					callback: _cleanup
				}],
				layout: ['__message', 'device', 'pool', 'volumeFilename', 'paravirtual', 'driver_cache']
			});

			// hide pool for block devices
			form._widgets.pool.set( 'visible', disk.type != 'block' );
			form._widgets.driver_cache.set('visible', this.domain.domain_type == 'kvm');

			_dialog = new Dialog({
				title: _('Edit drive'),
				content: form,
				'class' : 'umcPopup',
				style: 'max-width: 400px;'
			});
			_dialog.show();
		},

		_removeDrive: function( ids, items ) { 
			var disk = items[ 0 ];

			var buttons = [ {
				name: 'detach',
				label: _('Detach')
			}, {
				name: 'delete',
				label: _('Delete')
			}, {
				name: 'cancel',
				'default': true,
				label: _('Cancel')
			} ];

			// confirm removal of drive
			var msg = _( 'Should the selected drive be deleted or detached from the virtual instance?' );
			// chain the UMCP commands for removing the drive
			var deferred = new Deferred();
			deferred.resolve();
			// just of a domain URI is available we need to detach/delete it otherwise we just remove it from the grid
			if ( undefined !== this.domain.domainURI ) {
				deferred = deferred.then( lang.hitch( this, function() {
					return tools.umcpCommand('uvmm/storage/volume/deletable', [ {
						domainURI: this.domain.domainURI,
						volumeFilename: disk.volumeFilename,
						pool: disk.pool
					} ] );
				} ) );
				deferred = deferred.then( lang.hitch( this, function( response ) {
					if ( disk.device == 'cdrom' ) {
						msg += ' ' + _( 'The selected drive is a CD-ROM and should be detached from the virtual instance. If the volume is delete no other instance can use it anymore.' );
					} else if ( ! response.result[ 0 ].deletable ) {
						msg += ' ' + _( 'The selected drive seems to be attached to other virtual instances and therefor should not be deleted.' );
					}
					return dialog.confirm( msg, buttons );
				} ) );

				deferred = deferred.then( lang.hitch( this, function( action ) {
					if ( action != 'delete' && action != 'detach' ) {
						return;
					}
					this.onUpdateProgress( 0, 1 );

					// detach the drive from the domain
					this.moduleStore.remove( ids[ 0 ] );

					if ( action == 'delete' ) {
						tools.umcpCommand('uvmm/storage/volume/remove', {
							nodeURI: this.domain.nodeURI,
							volumes: [ { pool: disk.pool, volumeFilename: disk.volumeFilename } ],
							pool: disk.pool
						} ).then( lang.hitch( this, function( response ) {
							this.onUpdateProgress( 1, 1 );
						} ) );
					} else {
						this.onUpdateProgress( 1, 1 );
					}
				} ) );
			} else {
				// detach the drive from the domain
				this.moduleStore.remove( ids[ 0 ] );
				this.onUpdateProgress( 1, 1 );
			}
		},

		_addDrive: function() {
			var _dialog = null, wizard = null;

			var _cleanup = function() {
				_dialog.hide();
				_dialog.destroyRecursive();
				wizard.destroyRecursive();
			};

			var _finished = lang.hitch(this, function(values) {
				var paravirtual = false;
				var driver_cache = values.device == 'disk' ? 'none' : 'default';
				var id = this._nextID();

				_cleanup();
				if ( this.domain.profileData ) {
					if ( values.device == 'cdrom' && this.domain.profileData.pvcdrom ) {
						paravirtual = true;
					} else if ( values.device == 'disk' && this.domain.profileData.pvdisk ) {
						paravirtual = true;
					}
					if (undefined !== this.domain.profileData.drivercache && values.device == 'disk') {
						driver_cache = this.domain.profileData.drivercache || driver_cache;
					}
				}
				this.moduleStore.add( lang.mixin( {
					$id$: id,
					driver_cache: driver_cache,
					paravirtual: paravirtual
				}, values ) );
			});

			wizard = new DriveWizard({
				style: 'width: 450px; height:450px;',
				domain: this.domain,
				onFinished: _finished,
				onCancel: _cleanup
			});

			_dialog = new Dialog({
				title: _('Add a new drive'),
				content: wizard
			});
			_dialog.show();
		},

		filter: function() {
			this.inherited(arguments, [{}]);
		},

		onUpdateProgress: function(i, n) {
			// event stub
		}
	});
});
