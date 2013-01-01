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
/*global define window require*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/string",
	"dojo/Deferred",
	"dojox/html/entities",
	"dojox/string/sprintf",
	"dijit/Menu",
	"dijit/MenuItem",
	"dijit/layout/ContentPane",
	"dijit/ProgressBar",
	"dijit/Dialog",
	"dijit/form/_TextBoxMixin",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/Module",
	"umc/widgets/Page",
	"umc/widgets/Form",
	"umc/widgets/ExpandingTitlePane",
	"umc/widgets/Grid",
	"umc/widgets/SearchForm",
	"umc/widgets/Tree",
	"umc/widgets/Tooltip",
	"umc/widgets/Text",
	"umc/widgets/ContainerWidget",
	"umc/widgets/CheckBox",
	"umc/widgets/ComboBox",
	"umc/widgets/TextBox",
	"umc/modules/uvmm/TreeModel",
	"umc/modules/uvmm/DomainPage",
	"umc/modules/uvmm/DomainWizard",
	"umc/modules/uvmm/types",
	"umc/i18n!umc/modules/uvmm"
], function(declare, lang, array, string, Deferred, entities, sprintf, Menu, MenuItem, ContentPane, ProgressBar, Dialog, _TextBoxMixin,
	tools, dialog, Module, Page, Form, ExpandingTitlePane, Grid, SearchForm, Tree, Tooltip, Text, ContainerWidget,
	CheckBox, ComboBox, TextBox, TreeModel, DomainPage, DomainWizard, types, _) {

	return declare("umc.modules.uvmm", [ Module ], {

		// the property field that acts as unique identifier
		idProperty: 'id',

		// internal reference to the search page
		_searchPage: null,

		// internal reference to the detail page for editing an UDM object
		_domainPage: null,

		// reference to a `umc.widgets.Tree` instance which is used to display the container
		// hierarchy for the UDM navigation module
		_tree: null,

		// reference to the last item in the navigation on which a context menu has been opened
		_navContextItem: null,

		_finishedDeferred: null,
		_ucr: null,

		_progressBar: null,
		_progressContainer: null,

		uninitialize: function() {
			this.inherited(arguments);

			this._progressContainer.destroyRecursive();
		},

		postMixInProperties: function() {
			this.inherited(arguments);
		},

		buildRendering: function() {
			// call superclass method
			this.inherited(arguments);

			// load asynchronously some UCR variables
			this._finishedDeferred = new Deferred();
			tools.ucr('uvmm/umc/*').then(lang.hitch(this, function(ucr) {
				this._ucr = ucr;
				this._finishedDeferred.resolve(this._ucr);
			}));

			// setup search page
			this._searchPage = new Page({
				headerText: 'UCS Virtual Machine Manager'
				//helpText: _('<p>This module provides a management interface for physical servers that are registered within the UCS domain.</p><p>The tree view on the left side shows an overview of all existing physical servers and the residing virtual instances. By selecting one of the physical servers statistics of the current state are displayed to get an impression of the health of the hardware system. Additionally actions like start, stop, suspend and resume for each virtual instance can be invoked on each of the instances.</p><p>Also possible is direct access to virtual instances. Therefor it must be activated in the configuration.</p><p>Each virtual instance entry in the tree view provides access to detailed information und gives the possibility to change the configuration or state and migrated it to another physical server.</p>')
			});
			this.addChild(this._searchPage);
			var titlePane = new ExpandingTitlePane({
				title: _('Search for virtual instances and physical servers'),
				design: 'sidebar'
			});
			this._searchPage.addChild(titlePane);

			//
			// add data grid
			//

			// search widgets
			var widgets = [{
				type: ComboBox,
				name: 'type',
				label: _('Displayed type'),
				staticValues: [
					{ id: 'domain', label: _('Virtual instance') },
					{ id: 'node', label: _('Physical server') }
				],
				size: 'Half'
			}, {
				type: TextBox,
				name: 'pattern',
				label: _('Query pattern'),
				size: 'One',
				value: '*'
			}];
			var layout = [[ 'type', 'pattern', 'submit' ]];

			// generate the search widget
			this._searchForm = new SearchForm({
				region: 'top',
				widgets: widgets,
				layout: layout,
				onSearch: lang.hitch(this, 'filter')
			});
			titlePane.addChild(this._searchForm);

			// generate the data grid
			this._finishedDeferred.then( lang.hitch( this, function( ucr ) {
				this._grid = new Grid({
					region: 'center',
					actions: this._getGridActions('domain'),
					actionLabel: ucr[ 'uvmm/umc/action/label' ] != 'no', // hide labels of action columns
					columns: this._getGridColumns('domain'),
					moduleStore: this.moduleStore
					/*footerFormatter: lang.hitch(this, function(nItems, nItemsTotal) {
					// generate the caption for the grid footer
					if (0 === nItemsTotal) {
					return _('No %(objPlural)s could be found', map);
					}
					else if (1 == nItems) {
					return _('%(nSelected)d %(objSingular)s of %(nTotal)d selected', map);
					}
					else {
					return _('%(nSelected)d %(objPlural)s of %(nTotal)d selected', map);
					}
					}),*/
				});

				titlePane.addChild(this._grid);

				// register event
				this._grid.on('FilterDone', lang.hitch(this, '_selectInputText')); // FIXME: ?
			} ) );
			// generate the navigation tree
			var model = new TreeModel({
				umcpCommand: lang.hitch(this, 'umcpCommand')
			});
			this._tree = new Tree({
				//style: 'width: auto; height: auto;',
				model: model,
				persist: false,
				showRoot: false,
				autoExpand: true,
				path: [ model.root.id, 'default' ],
				// customize the method getIconClass()
				//onClick: lang.hitch(this, 'filter'),
				getIconClass: lang.hitch(this, function(/*dojo.data.Item*/ item, /*Boolean*/ opened) {
					return tools.getIconClass(this._iconClass(item));
				})
			});
			var treePane = new ContentPane({
				content: this._tree,
				region: 'left',
				splitter: true,
				style: 'width: 200px;'
			});
			titlePane.addChild(treePane);

			// add a context menu to edit/delete items
			var menu = new Menu({});
	/*		menu.addChild(new MenuItem({
				label: _( 'Edit' ),
				iconClass: 'umcIconEdit',
				onClick: lang.hitch(this, function(e) {
					this.createDomainPage(this._navContextItem.objectType, this._navContextItem.id);
				})
			}));
			menu.addChild(new MenuItem({
				label: _( 'Delete' ),
				iconClass: 'umcIconDelete',
				onClick: lang.hitch(this, function() {
					this.removeObjects(this._navContextItem.id);
				})
			}));*/
			menu.addChild(new MenuItem({
				label: _( 'Reload' ),
				iconClass: 'umcIconRefresh',
				onClick: lang.hitch(this, function() {
					this._tree.reload();
				})
			}));

			// when we right-click anywhere on the tree, make sure we open the menu
			menu.bindDomNode(this._tree.domNode);

			// remember on which item the context menu has been opened
			/*aspect.after(menu, '_openMyself', lang.hitch(this, function(e) { // TODO: require dojo/aspect if uncomment
				var el = registry.getEnclosingWidget(e.target); // TODO: require dijit/registry if uncomment
				if (el) {
					this._navContextItem = el.item;
				}
			}));*/

			this._searchPage.startup();

			// setup a progress bar with some info text
			this._progressContainer = new ContainerWidget({});
			this._progressBar = new ProgressBar({
				style: 'background-color: #fff;'
			});
			this._progressContainer.addChild(this._progressBar);
			this._progressContainer.addChild(new Text({
				content: _('Please wait, your requests are being processed...')
			}));

			// setup the detail page
			this._domainPage = new DomainPage({
				onClose: lang.hitch(this, function() {
					this.selectChild(this._searchPage);
					this.set( 'title', this.defaultTitle );
				}),
				moduleWidget: this
			});
			this.addChild(this._domainPage);

			// register events
			this._domainPage.on('UpdateProgress', lang.hitch(this, 'updateProgress'));
			this._searchPage.on('Show', lang.hitch(this, '_selectInputText'));
		},

		postCreate: function() {
			this.inherited(arguments);

			this.own(this._tree.watch('path', lang.hitch(this, function() {
				var searchType = this._searchForm.getWidget('type').get('value');
				if (searchType == 'domain') {
					this._finishedDeferred.then(lang.hitch(this, function(ucr) {
						if (tools.isTrue(ucr['uvmm/umc/autosearch'])) {
							this.filter();
						}
					}));
				}
			})));
		},

		_selectInputText: function() {
			// focus on input widget
			var widget = this._searchForm.getWidget('pattern');
			widget.focus();

			// select the text
			if (widget.textbox) {
				try {
					_TextBoxMixin.selectInputText(widget.textbox);
				}
				catch (err) { }
			}
		},

		vncLink: function( ids, items ) {
			tools.umcpCommand( 'uvmm/domain/get', { domainURI : ids[ 0 ] } ).then( lang.hitch( this, function( response ) {
				var w = window.open();
				var html = lang.replace( "<html><head><title>{domainName} on {nodeName}</title></head><body><applet archive='/TightVncViewer.jar' code='com.tightvnc.vncviewer.VncViewer' height='100%%' width='100%%'><param name='host' value='{vnc_host}' /><param name='port' value='{vnc_port}' /><param name='offer relogin' value='no' />VNC-Java-Applet does not work; try external VNC viewer <a href='vnc://{vnc_host}:{vnc_port}'>vnc://{vnc_host}:{vnc_port}</a>.</applet></body></html>", {
					domainName: entities.encode(items[ 0 ].label),
					nodeName: entities.encode(items[ 0 ].nodeName),
					vnc_host: entities.encode(response.result.vnc_host),
					vnc_port: response.result.vnc_port
				} );
				w.document.write( html );
				w.document.close();
			} ) );
		},

		_migrateDomain: function( ids, items ) {
			var _dialog = null, form = null;
			var unavailable = array.some( items, function( domain ) {
				return domain.node_available === false;
			} );
			if ( ids.length > 1 ) {
				var uniqueNodes = {}, count = 0;
				array.forEach( ids, function( id ) {
					var nodeURI = id.slice( 0, id.indexOf( '#' ) );
					if ( undefined === uniqueNodes[ nodeURI ] ) {
						++count;
					}
					uniqueNodes[ nodeURI ] = true;
				} );
				if ( count > 1 ) {
					dialog.alert( _( 'The selected virtual instances are not all located on the same physical server. The migration will not be performed.' ) );
					return;
				}
			}

			var _cleanup = function() {
				_dialog.hide();
				_dialog.destroyRecursive();
			};

			var _migrate = lang.hitch(this, function(name) {
				// send the UMCP command
				this.updateProgress(0, 1);
				tools.umcpCommand('uvmm/domain/migrate', {
					domainURI: ids[ 0 ],
					targetNodeURI: name
				}).then(lang.hitch(this, function() {
					this.moduleStore.onChange();
					this.updateProgress(1, 1);
				}), lang.hitch(this, function() {
					this.moduleStore.onChange();
					this.updateProgress(1, 1);
				}));
			});

			var sourceURI = ids[ 0 ].slice( 0, ids[ 0 ].indexOf( '#' ) );
			var sourceScheme = types.getNodeType( sourceURI );
			form = new Form({
				style: 'max-width: 500px;',
				widgets: [ {
					type: Text,
					name: 'warning',
					content: _( '<p>For fail over the virtual machine can be migrated to another physical server re-using the last known configuration and all disk images. This can result in <strong>data corruption</strong> if the images are <strong>concurrently used</strong> by multiple running instances! Therefore the failed server <strong>must be blocked from accessing the image files</strong>, for example by blocking access to the shared storage or by disconnecting the network.</p><p>When the server is restored, all its previous virtual instances will be shown again. Any duplicates have to be cleaned up manually by migrating the instances back to the server or by deleting them. Make sure that shared images are not delete.</p>' )
				}, {
					name: 'name',
					type: ComboBox,
					label: _('Please select the destination server:'),
					dynamicValues: function() {
						return types.getNodes().then( function( items ) {
							return array.filter( items, function( item ) {
								return item.id != sourceURI && types.getNodeType( item.id ) == sourceScheme;
							} );
						} );
					}
				}],
				buttons: [{
					name: 'submit',
					label: _( 'Migrate' ),
					style: 'float: right;',
					callback: function() {
						var nameWidget = form.getWidget('name');
						if (nameWidget.isValid()) {
							var name = nameWidget.get('value');
							_cleanup();
							_migrate( name );
						}
					}
				}, {
					name: 'cancel',
					label: _('Cancel'),
					callback: _cleanup
				}],
				layout: [ 'warning', 'name' ]
			});

			form._widgets.warning.set( 'visible', unavailable );
			_dialog = new Dialog({
				title: _('Migrate domain'),
				content: form,
				'class': 'umcPopup'
			});
			_dialog.show();
		},

		_removeDomain: function( ids, items ) {
			var _dialog = null, form = null;
			var domain = items[ 0 ];
			var domain_details = null;
			var domainURI = ids[ 0 ];
			var widgets = [
				{
					type: Text,
					name: 'question',
					content: '<p>' + lang.replace( _( 'Should the selected virtual instance {label} be removed?' ), {
						label: entities.encode(domain.label)
					} ) + '</p>',
					label: ''
				} ];
			var _widgets = null;
			var drive_list = [];

			var _cleanup = function() {
				_dialog.hide();
				form.destroyRecursive();
			};

			var _remove = lang.hitch( this, function() {
				this.updateProgress( 0, 1 );
				var volumes = [];
				tools.forIn( form._widgets, lang.hitch( this, function( iid, iwidget ) {
					if ( iwidget instanceof CheckBox && iwidget.get( 'value' ) ) {
						volumes.push( iwidget.$id$ );
					}
				} ) );

				tools.umcpCommand('uvmm/domain/remove', {
					domainURI: domainURI,
					volumes: volumes
				} ).then( lang.hitch( this, function( response ) {
					this.updateProgress( 1, 1 );
					this.moduleStore.onChange();
				} ), lang.hitch( this, function() {
					this.updateProgress( 1, 1 );
				} ) );
			} );

			// chain the UMCP commands for removing the domain
			var deferred = new Deferred();
			deferred.resolve();

			// get domain details
			deferred = deferred.then( lang.hitch( this, function() {
				return tools.umcpCommand('uvmm/domain/get', { domainURI : domainURI } );
			} ) );
			// find the default for the drive checkboxes;
			deferred = deferred.then( lang.hitch( this, function( response ) {
				domain_details = response.result;
				var drive_list = array.map( response.result.disks, function( disk ) {
					return { domainURI : domainURI, pool : disk.pool, volumeFilename : disk.volumeFilename, source : disk.source };
				} );
				return tools.umcpCommand('uvmm/storage/volume/deletable', drive_list );
			} ) );
			// got response for UMCP request
			deferred = deferred.then( lang.hitch( this, function( response ) {
				var layout = [ 'question' ];
				var failed_disks = [];
				array.forEach( response.result, lang.hitch( this, function( disk ) {

					if ( null !== disk.deletable ) {
						layout.push( disk.source );
						widgets.push( {
							type: CheckBox,
							name: disk.source,
							label: lang.replace( _( '{volumeFilename} (Pool: {pool})' ), disk ),
							value: disk.deletable,
							$id$: { pool : disk.pool, volumeFilename : disk.volumeFilename }
						} );
					} else {
						failed_disks.push( disk.source );
						disk.pool = null === disk.pool ? _( 'Unknown' ) : disk.pool;
						widgets.push( {
							type: Text,
							name: disk.source,
							content: '<p>' + _( 'Not removable' ) + ': ' + lang.replace( _( '{volumeFilename} (Pool: {pool})' ), {
								volumeFilename: entities.encode(disk.volumeFilename),
								pool: entities.encode(disk.pool)
							} ) + '</p>',
							label: '',
							$id$: { pool : disk.pool, volumeFilename : disk.volumeFilename }
						} );
					}
				} ) );
				if ( failed_disks.length ) {
					layout = layout.concat( failed_disks );
				}

				form = new Form({
					widgets: widgets,
					buttons: [{
						name: 'submit',
						label: _( 'delete' ),
						style: 'float: right;',
						callback: function() {
							_cleanup();
							_remove();
						}
					}, {
						name: 'cancel',
						label: _('Cancel'),
						callback: _cleanup
					}],
					layout: layout
				});

				_dialog = new Dialog({
					title: _( 'Remove a virtual instance' ),
					content: form,
					'class' : 'umcPopup'
				});
				_dialog.show();
			} ) );

		},

		_addDomain: function() {
			var wizard = null;

			var _cleanup = lang.hitch(this, function() {
				this.selectChild(this._searchPage);
				this.removeChild(wizard);
				wizard.destroyRecursive();
			});

			var _finished = lang.hitch(this, function(values) {
				this.standby(true);
				tools.umcpCommand('uvmm/domain/add', {
					nodeURI: values.nodeURI,
					domain: values
				}).then(lang.hitch(this, function() {
					_cleanup();
					this.moduleStore.onChange();
					this.standby(false);
				}), lang.hitch(this, function() {
					this.standby(false);
				}));
			});

			wizard = new DomainWizard({
				onFinished: _finished,
				onCancel: _cleanup
			});
			this.addChild(wizard);
			this.selectChild(wizard);
		},

		_maybeChangeState: function(/*String*/ question, /*String*/ buttonLabel, /*String*/ newState, /*String*/ action, ids, items ) {
			var _dialog = null, form = null;

			var _cleanup = function() {
				_dialog.hide();
				form.destroyRecursive();
			};

			var sourceURI = ids[ 0 ].slice( 0, ids[ 0 ].indexOf( '#' ) );

			if ( ids.length > 1 ) {
				if ( ! this._grid.canExecuteOnSelection( action, items ).length ) {
					dialog.alert( _( 'The state of the selected virtual instances can not be changed' ) );
					return;
				}
			}

			form = new Form({
				widgets: [{
					name: 'question',
					type: Text,
					content: '<p>' + question + '</p>'
				}],
				buttons: [{
					name: 'submit',
					label: buttonLabel,
					style: 'float: right;',
					callback: lang.hitch( this, function() {
						_cleanup();
						this._changeState( newState, null, ids, items );
					} )
				}, {
					name: 'cancel',
					label: _('Cancel'),
					callback: _cleanup
				}],
				layout: [ 'question' ]
			});

			_dialog = new Dialog({
				title: _('Migrate domain'),
				content: form,
				'class': 'umcPopup',
				style: 'max-width: 400px;'
			});
			_dialog.show();
		},
		_changeState: function(/*String*/ newState, action, ids, items ) {
			// chain all UMCP commands
			var deferred = new Deferred();
			deferred.resolve();

			if ( ids.length > 1 && action !== null ) {
				if ( ! this._grid.canExecuteOnSelection( action, items ).length ) {
					dialog.alert( _( 'The state of the selected virtual instances can not be changed' ) );
					return;
				}
			}
			array.forEach(ids, function(iid, i) {
				deferred = deferred.then(lang.hitch(this, function() {
					this.updateProgress(i, ids.length);
					return tools.umcpCommand('uvmm/domain/state', {
						domainURI: iid,
						domainState: newState
					});
				}));
			}, this);

			// finish the progress bar and add error handler
			deferred = deferred.then(lang.hitch(this, function() {
				this.moduleStore.onChange();
				this.updateProgress(ids.length, ids.length);
			}), lang.hitch(this, function(error) {
				this.moduleStore.onChange();
				this.updateProgress(ids.length, ids.length);
			}));
		},

		_cloneDomain: function( ids ) {
			var _dialog = null, form = null;

			var _cleanup = function() {
				_dialog.hide();
				form.destroyRecursive();
			};

			var _createClone = lang.hitch(this, function( name, mac_address ) {
				// send the UMCP command
				this.updateProgress(0, 1);
				tools.umcpCommand('uvmm/domain/clone', {
					domainURI: ids[ 0 ],
					cloneName: name,
					macAddress: mac_address
				}).then(lang.hitch(this, function() {
					this.moduleStore.onChange();
					this.updateProgress(1, 1);
				}), lang.hitch(this, function(error) {
					this.moduleStore.onChange();
					this.updateProgress(1, 1);
				}));
			});

			form = new Form({
				widgets: [{
					name: 'name',
					type: TextBox,
					label: _('Please enter the name for the clone:'),
					regExp: '^[^./][^/]*$',
					invalidMessage: _('A valid clone name cannot contain "/" and may not start with "." .')
				}, {
					name: 'mac_address',
					type: ComboBox,
					label: _( 'MAC addresses' ),
					staticValues: [
						{ id : 'clone', label : _( 'Inherit MAC addresses' ) },
						{ id : 'auto', label : _( 'Generate new MAC addresses' ) }
					]
				} ],
				buttons: [{
					name: 'submit',
					label: _('Create'),
					style: 'float: right;',
					callback: function() {
						var nameWidget = form.getWidget('name');
						var macWidget = form.getWidget('mac_address');
						if (nameWidget.isValid()) {
							var name = nameWidget.get('value');
							_cleanup();
							_createClone( name, macWidget.get( 'value' ) );
						}
					}
				}, {
					name: 'cancel',
					label: _('Cancel'),
					callback: _cleanup
				}],
				layout: [ 'name', 'mac_address' ]
			});

			_dialog = new Dialog({
				title: _('Create a clone'),
				content: form,
				'class': 'umcPopup'
			});
			_dialog.show();
		},

		openDomainPage: function(ids) {
			if (!ids.length) {
				return;
			}
			this._domainPage.load(ids[0]);
			this.selectChild(this._domainPage);
		},

		_getGridColumns: function(type) {
			if (type == 'node') {
				return [{
					name: 'label',
					label: _('Name'),
					formatter: lang.hitch(this, 'iconFormatter')
				}, {
					name: 'cpuUsage',
					label: _('CPU usage'),
					width: 'adjust',
					formatter: lang.hitch(this, 'cpuUsageFormatter')
				}, {
					name: 'memUsed',
					label: _('Memory usage'),
					width: 'adjust',
					formatter: lang.hitch(this, 'memoryUsageFormatter')
				}];
			}

			// else type == 'domain'
			return [{
				name: 'label',
				label: _('Name'),
				formatter: lang.hitch(this, 'iconFormatter')
			}, {
				name: 'cpuUsage',
				label: _('CPU usage'),
				style: 'min-width: 80px;',
				width: 'adjust',
				formatter: lang.hitch(this, 'cpuUsageFormatter')
			}];
		},

		_getGridActions: function(type) {
			if (type == 'node') {
				// we do not have any actions for nodes
				return [];
			}

			// else type == 'domain'
			// STATES = ( 'NOSTATE', 'RUNNING', 'IDLE', 'PAUSED', 'SHUTDOWN', 'SHUTOFF', 'CRASHED' )
			return [{
				name: 'edit',
				label: _( 'Edit' ),
				isStandardAction: true,
				isMultiAction: false,
				iconClass: 'umcIconEdit',
				description: _( 'Edit the configuration of the virtual instance' ),
				callback: lang.hitch(this, 'openDomainPage')
			}, {
				name: 'start',
				label: _( 'Start' ),
				iconClass: 'umcIconPlay',
				description: _( 'Start the virtual instance' ),
				isStandardAction: true,
				isMultiAction: true,
				callback: lang.hitch(this, '_changeState', 'RUN', 'start' ),
				canExecute: function(item) {
					return item.state != 'RUNNING' && item.state != 'IDLE' && item.node_available;
				}
			}, {
				name: 'stop',
				label: _( 'Stop' ),
				iconClass: 'umcIconStop',
				description: _( 'Shut off the virtual instance' ),
				isStandardAction: false,
				isMultiAction: true,
				callback: lang.hitch(this, '_maybeChangeState', _( 'Stopping virtual instances will turn them off without shutting down the operating system. Should the operation be continued?' ), _( 'Stop' ), 'SHUTDOWN', 'stop' ),
				canExecute: function(item) {
					return item.state == 'RUNNING' || item.state == 'IDLE' && item.node_available;
				}
			}, {
				name: 'pause',
				label: _( 'Pause' ),
				iconClass: 'umcIconPause',
				isStandardAction: false,
				isMultiAction: true,
				callback: lang.hitch(this, '_changeState', 'PAUSE', 'pause' ),
				canExecute: function(item) {
					return item.state == 'RUNNING' || item.state == 'IDLE' && item.node_available;
				}
			}, {
				name: 'suspend',
				label: _( 'Suspend' ),
				// iconClass: 'umcIconPause',
				isStandardAction: false,
				isMultiAction: true,
				callback: lang.hitch(this, '_changeState', 'SUSPEND', 'suspend' ),
				canExecute: function(item) {
					return ( item.state == 'RUNNING' || item.state == 'IDLE' ) && types.getNodeType( item.id ) == 'qemu' && item.node_available;
				}
			}, /* { FIXME: not yet fully supported
				name: 'restart',
				label: _( 'Restart' ),
				isStandardAction: false,
				isMultiAction: true,
				callback: lang.hitch(this, '_changeState', 'RESTART', 'restart' ),
				canExecute: function(item) {
					return item.state == 'RUNNING' || item.state == 'IDLE';
				}
			}, */ {
				name: 'clone',
				label: _( 'Clone' ),
				isStandardAction: false,
				isMultiAction: false,
				callback: lang.hitch(this, '_cloneDomain' ),
				canExecute: function(item) {
					return item.state == 'SHUTOFF' && item.node_available;
				}
			}, {
				name: 'vnc',
				label: _( 'View' ),
				isStandardAction: true,
				isMultiAction: false,
				iconClass: 'umcIconView',
				description: lang.hitch( this, function( item ) {
					return lang.replace( _( 'Open a view to the virtual instance {label} on {nodeName}' ), item );
				} ),
				callback: lang.hitch(this, 'vncLink' ),
				canExecute: function(item) {
					return ( item.state == 'RUNNING' || item.state == 'IDLE' ) && item.vnc_port && item.node_available;
				}
			}, {
				name: 'migrate',
				label: _( 'Migrate' ),
				isStandardAction: false,
				isMultiAction: true,
				callback: lang.hitch(this, '_migrateDomain' ),
				canExecute: function(item) {
					return item.state != 'PAUSE'; // FIXME need to find out if there are more than one node of this type
				}
			}, {
				name: 'remove',
				label: _( 'Remove' ),
				isStandardAction: false,
				isMultiAction: false,
				callback: lang.hitch(this, '_removeDomain' ),
				canExecute: function(item) {
					return item.state == 'SHUTOFF' && item.node_available;
				}
			}, {
				name: 'add',
				label: _( 'Create virtual instance' ),
				iconClass: 'umcIconAdd',
				isMultiAction: false,
				isContextAction: false,
				callback: lang.hitch(this, '_addDomain' )
			}];
		},

		cpuUsageFormatter: function(id, rowIndex) {
			// summary:
			//		Formatter method for cpu usage.

			var item = this._grid._grid.getItem(rowIndex);
			var percentage = Math.round(item.cpuUsage);

			if (item.state == 'RUNNING' || item.state == 'IDLE') {
				// only show CPU info, if the machine is running
				return new ProgressBar({
					value: percentage + '%'
				});
			}

			return '';
		},

		memoryUsageFormatter: function(id, rowIndex) {
			// summary:
			//		Formatter method for memory usage.

			var item = this._grid._grid.getItem(rowIndex);
			if (item.type == 'node') {
				// for the node, return a progressbar
				var percentage = Math.round(item.cpuUsage);
				return new ProgressBar({
					label: sprintf('%.1f GB / %.1f GB', item.memUsed / 1073741824.0, item.memAvailable / 1073741824.0),
					maximum: item.memAvailable,
					value: item.memUsed
				});
			}

			// else: item.type == 'domain'
			// for the domain, return a simple string
			return sprintf('%.1f GB', (item.mem || 0) / 1073741824.0);
		},

		_iconClass: function(item) {
			var iconName = 'uvmm-' + item.type;
			if (item.type == 'node') {
				if (item.virtech) {
					iconName += '-' + item.virtech;
				}
				if (!item.available) {
					iconName += '-off';
				}
			}
			else if (item.type == 'domain') {
				if ( !item.node_available ) {
					iconName += '-off';
				} else if (item.state == 'RUNNING' || item.state == 'IDLE') {
					iconName += '-on';
				}
				else if ( item.state == 'PAUSED' || ( item.state == 'SHUTOFF' && item.suspended ) ) {
					iconName += '-paused';
				}
			}
			return iconName;
		},

		iconFormatter: function(label, rowIndex) {
			// summary:
			//		Formatter method that adds in a given column of the search grid icons
			//		according to the object types.

			// create an HTML image that contains the icon (if we have a valid iconName)
			var item = this._grid._grid.getItem(rowIndex);
			var html = string.substitute('<img src="${themeUrl}/icons/16x16/${icon}.png" height="${height}" width="${width}" style="float:left; margin-right: 5px" /> ${label}', {
				icon: this._iconClass(item),
				height: '16px',
				width: '16px',
				label: label,
				themeUrl: require.toUrl('dijit/themes/umc')
			});
			// set content after creating the object because of HTTP404: Bug #25635
			var widget = new Text({});
			widget.set('content', html);

			if ( undefined !== item.state ) {
				var tooltip = new Tooltip( {
					label: lang.replace( _( 'State: {state}<br>Server: {node}<br>{vnc_port}' ), {
						state: types.getDomainStateDescription( item ),
						node: item.nodeName,
						vnc_port: item.vnc_port == -1 ? '' : _( 'VNC-Port: %s', item.vnc_port)
					} ),
					connectId: [ widget.domNode ],
					position: [ 'below' ]
				});

				// destroy the tooltip when the widget is destroyed
				tooltip.connect( widget, 'destroy', 'destroy' );
			}

			return widget;
		},

		filter: function() {
			// summary:
			//		Send a new query with the given filter options as specified in the search form
			//		and the selected server/group.

			// validate the search form
			var _vals = this._searchForm.gatherFormValues();
			_vals.pattern = _vals.pattern === '' ? '*' : _vals.pattern;
			if (!this._searchForm.getWidget('type').isValid()) {
				dialog.alert(_('Please select a valid search type.'));
				return;
			}

			var path = this._tree.get('path');
			var treeType = 'root';
			var treeID = '';
			if (path.length) {
				var item = path[path.length - 1];
				treeType = item.type || 'node';
				treeID = item.id;
			}

			// build the query we need to send to the server
			var vals = {
				type: _vals.type,
				domainPattern: '*',
				nodePattern: '*'
			};
			if (vals.type == 'domain') {
				vals.domainPattern = _vals.pattern;
			}
			else {
				vals.nodePattern = _vals.pattern;
			}
			if (treeType == 'node' && vals.type == 'domain') {
				// search for domains only in the scope of the given node
				vals.nodePattern = treeID;
			}

			this._grid.filter(vals);

			// update tree
			if ( treeType == 'node' && treeID ) {
				tools.umcpCommand( 'uvmm/node/query', { nodePattern: treeID } ).then( lang.hitch( this, function( response ) {
					this._tree.model.changes( response.result );
				} ) );
			} else if ( treeType == 'group' ) {
				tools.umcpCommand( 'uvmm/node/query', { nodePattern: "*" } ).then( lang.hitch( this, function( response ) {
					this._tree.model.changes( response.result );
				} ) );
			}
			// update the grid columns
			this._grid.setColumnsAndActions(this._getGridColumns(vals.type), this._getGridActions(vals.type));
		},

		updateProgress: function(i, n) {
			var progress = this._progressBar;
			if (i === 0) {
				// initiate the progressbar and start the standby
				progress.set('maximum', n);
				progress.set('value', 0);
				this.standby(true, this._progressContainer);
			}
			else if (i >= n || i < 0) {
				// finish the progress bar
				progress.set('value', n);
				this.standby(false);
			}
			else {
				progress.set('value', i);
			}
		}
	});
});
