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
	"dojo/store/Memory",
	"dojo/store/Observable",
	"umc/tools",
	"umc/widgets/TitlePane",
	"umc/widgets/Wizard",
	"umc/widgets/ContainerWidget",
	"umc/modules/uvmm/DriveGrid",
	"umc/modules/uvmm/types",
	"umc/i18n!umc/modules/uvmm"
], function(declare, lang, array, Memory, Observable, tools, TitlePane, Wizard, ContainerWidget, DriveGrid, types, _) {

	return declare("umc.modules.uvmm.DomainWizard", [ Wizard ], {
		_profile: null,

		_driveStore: null,
		_driveGrid: null,
		_driveContainer: null,

		constructor: function() {
			// grid for the drives
			this._driveStore = new Observable(new Memory({
				idProperty: '$id$'
			}));
			this._driveGrid = new DriveGrid({
				moduleStore: this._driveStore
			});

			// wrap grid in a titlepane
			var titlePane = new TitlePane({
				title: _('Drives')
			});
			titlePane.addChild(this._driveGrid);

			// and the titlepane into a container
			this._driveContainer  = new ContainerWidget({
				scrollable: true,
				region: 'center'
			});
			this._driveContainer.addChild(titlePane);

			// mixin the page structure
			lang.mixin(this, {
				pages: [{
					name: 'profile',
					headerText: _('Create a virtual instance'),
					helpText: _('By selecting a profile for the virtual instance most of the settings will be set to default values. In the following steps some of these values might be modified. After the creation of the virtual instance all parameters, extended settings und attached drives can be adjusted. It should be ensured that the profile is for the correct architecture as this option can not be changed afterwards.'),
					widgets: [{
						name: 'nodeURI',
						type: 'ComboBox',
						label: _('Physical server'),
						dynamicValues: types.getNodes
					}, {
						name: 'profileDN',
						type: 'ComboBox',
						label: _('Profile'),
						depends: 'nodeURI',
						dynamicValues: types.getProfiles
					}]
				}, {
					name: 'general',
					headerText: '...',
					helpText: _('The following settings were read from the selected profile and can be modified now.'),
					widgets: [{
						name: 'nodeURI',
						type: 'HiddenInput'
					}, {
						name: 'profile',
						type: 'HiddenInput'
					}, {
						name: 'domain_type',
						type: 'HiddenInput'
					}, {
						name: 'name',
						type: 'TextBox',
						required: true,
						invalidMessage: _( 'A name for the virtual instance is required and should not be the same as the given name prefix' ),
						label: _('Name')
					}, {
						name: 'description',
						type: 'TextBox',
						label: _('Description')
					}, {
						name: 'maxMem',
						type: 'TextBox',
						required: true,
						constraints: {min: 4*1024*1024},
						validator: function(value, constraints) {
							var size = types.parseStorageSize(value);
							if (size === null) {
								return false;
							}
							if (/[0-9]+(?:[,.][0-9]+)?[ \t]*$/.test(value)) {
								size *= 1024 * 1024;
							}
							if (constraints.min && size < constraints.min) {
								return false;
							}
							if (constraints.max && size > constraints.max) {
								return false;
							}
							return true;
						},
						invalidMessage: _('The memory size is invalid (e.g. 3GB or 1024 MB), minimum 4 MB'),
						label: _('Memory (default unit MB)')
					}, {
						name: 'vcpus',
						type: 'ComboBox',
						label: _('Number of CPUs'),
						depends: 'nodeURI',
						dynamicValues: types.getCPUs
					}, {
						name: 'vnc',
						type: 'CheckBox',
						label: _('Enable direct access')
					}]
				}, {
					name: 'drives',
					headerText: _('Add drive'),
					helpText: _('To finalize the creation of the virtual instance, please add one or more drives by clicking on "Add drive".')
				}]
			});
		},

		buildRendering: function() {
			this.inherited(arguments);

			// add the drive grid to the last page
			this._pages.drives.addChild(this._driveContainer);

			// connect to the onShow method of the drives page to adjust the size of the grid
			this._pages.drives.on('show', lang.hitch(this, function() {
				this._driveGrid.resize();
			}));
		},

		next: function(pageName) {
			var nextName = this.inherited(arguments);
			if (pageName == 'profile') {
				// query the profile settings
				this.standby(true);
				var profileDN = this.getWidget('profileDN').get('value');
				tools.umcpCommand('uvmm/profile/get', {
					profileDN: profileDN
				}).then(lang.hitch(this, function(data) {
					// we got the profile...
					this._profile = data.result;
					this._profile.profileDN = profileDN;

					// pre-set the form fields
					var nodeURI = this.getWidget('profile', 'nodeURI').get('value');
					this.getWidget('general', 'nodeURI').set('value', nodeURI);
					this.getWidget('profile').set('value', profileDN);
					this.getWidget('domain_type').set('value', this._profile.virttech.split('-')[0]);
					this.getWidget('name').set('value', this._profile.name_prefix || '');
					if (types.getNodeType(nodeURI) == 'xen') {
						this.getWidget('name').set('regExp', this._profile.name_prefix ? '^(?!' + this._profile.name_prefix + '$)[A-Za-z0-9_\\-.:+]+$' : '.*');
					} else {
						this.getWidget('name').set('regExp', this._profile.name_prefix ? '^(?!' + this._profile.name_prefix + '$)[^./][^/]*$' : '.*');
					}
					this.getWidget('maxMem').set('value', this._profile.ram || '');
					this.getWidget('vcpus').set('value', this._profile.cpus);
					this.getWidget('vnc').set('value', this._profile.vnc);

					// update page header
					this._pages.general.set('headerText', _('Create a virtual instance (profile: %s)', this._profile.name));

					this.standby(false);
				}), lang.hitch(this, function() {
					// fallback... switch off the standby animation
					this.standby(false);
				}));
			}
			else if (pageName == 'general') {
				// update the domain info for the drive grid
				array.forEach( [ 'name', 'maxMem' ], lang.hitch( this, function( widgetName ) {
					if ( ! this.getWidget( widgetName ).isValid() ) {
						this.getWidget( widgetName ).focus();
						nextName = null;
						return false;
					}
				} ) );

				if ( null !== nextName ) {
					this._driveGrid.domain = this.getValues();
					this._driveGrid.domain.nodeURI = this.getWidget( 'nodeURI' ).get( 'value' );
					this._driveGrid.domain.profileData = this._profile;
				}
			}

			return nextName;
		},

		getValues: function() {
			var values = this._pages.general._form.gatherFormValues();
			values.nodeURI = this.getWidget('nodeURI').get('value');
			values.vnc_remote = true;
			values.disks = this._driveStore.data;

			// add standard interface
			values.interfaces = [{
				model: types.getDefaultInterfaceModel(this.getWidget('domain_type').get('value'), this._profile.pvinterface),
				source: this._profile['interface']
			}];
			return values;
		}
	});
});
