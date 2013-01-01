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
	"dojox/string/sprintf",
	"umc/dialog",
	"umc/tools",
	"umc/store",
	"umc/widgets/Grid",
	"umc/widgets/TabbedModule",
	"umc/widgets/Page",
	"umc/modules/quota/PageContainer",
	"umc/widgets/ExpandingTitlePane",
	"umc/i18n!umc/modules/quota"
], function(declare, lang, array, sprintf, dialog, tools, store, Grid, TabbedModule, Page, PageContainer, ExpandingTitlePane, _) {

	return declare("umc.modules.quota", [ TabbedModule ], {

		idProperty: 'partitionDevice',
		moduleStore: null,
		_overviewPage: null,
		_pageContainer: null,

		buildRendering: function() {
			this.inherited(arguments);
			this.renderOverviewPage();
		},

		postMixInProperties: function() {
			this.inherited(arguments);
			this.moduleStore = store(this.idProperty, this.moduleID + '/partitions');
		},

		renderOverviewPage: function() {
			this._overviewPage = new Page({
				title: _('Partitions'),
				moduleStore: this.moduleStore,
				headerText: _('List partitions'),
				helpText: _('Set, unset and modify filesystem quota')
			});
			this.addChild(this._overviewPage);

			var titlePane = new ExpandingTitlePane({
				title: _('Partition overview')
			});
			this._overviewPage.addChild(titlePane);

			var actions = [{
				name: 'activate',
				label: lang.hitch(this, function(item) {
					if (item === undefined) {
						return _('(De)activate');
					} else if (item.inUse === true) {
						return _('Deactivate');
					} else {
						return _('Activate');
					}
				}),
				isStandardAction: true,
				canExecute: function(item) {
					if (item.mountPoint == '/') {
						return false;
					} else {
						return true;
					}
				},
				callback: lang.hitch(this, function(partitionDevice) {
					var doActivate = true;
					var item = this._grid.getItem(partitionDevice);
					if (item.inUse === true) {
						doActivate = false;
					}
					this.activateQuota(partitionDevice, doActivate);
				})
			}, {
				name: 'edit',
				label: _('Configure'),
				iconClass: 'umcIconEdit',
				isStandardAction: true,
				isMultiAction: false,
				canExecute: function(item) {
					if (item.inUse === true && item.mountPoint != '/') {
						return true;
					} else {
						return false;
					}
				},
				callback: lang.hitch(this, function(partitionDevice) {
					this.createPageContainer(partitionDevice[0]);
				})
			}, {
				name: 'refresh',
				label: _('Refresh'),
				isContextAction: false,
				isStandardAction: true,
				isMultiAction: false,
				callback: lang.hitch(this, function() {
					this._grid.filter({'dummy': 'dummy'});
				})
			}];

			var columns = [{
				name: 'partitionDevice',
				label: _('Partition'),
				width: 'auto'
			}, {
				name: 'mountPoint',
				label: _('Mount point'),
				width: 'auto'
			}, {
				name: 'inUse',
				label: _('Quota'),
				width: '85px',
				formatter: lang.hitch(this, function(value) {
					if (value === null) {
						return _('Unknown');
					} else if (value === true) {
						return _('Activated');
					} else {
						return _('Deactivated');
					}
				})
			}, {
				name: 'partitionSize',
				label: _('Size (GB)'),
				width: 'adjust',
				formatter: function(value) {
					if (value === null) {
						return '-';
					} else {
						return sprintf('%.1f', value);
					}
				}
			}, {
				name: 'freeSpace',
				label: _('Free (GB)'),
				width: 'adjust',
				formatter: function(value) {
					if (value === null) {
						return '-';
					} else {
						return sprintf('%.1f', value);
					}
				}
			}];

			this._grid = new Grid({
				region: 'center',
				actions: actions,
				columns: columns,
				moduleStore: this.moduleStore,
				query: {
					dummy: 'dummy'
				}
			});
			titlePane.addChild(this._grid);
			this._grid.on('FilterDone', lang.hitch(this, function() {
				var gridItems = this._grid.getAllItems(); // TODO rename?
				array.forEach(gridItems, lang.hitch(this, function(item) {
					if (item.inUse === null) {
						this._grid.setDisabledItem(item.partitionDevice, true);
					}
				}));
			}));

			this._overviewPage.startup();
		},

		activateQuota: function(partitionDevice, doActivate) {
			var dialogMessage = '';
			if (doActivate === true) {
				dialogMessage = _('Please confirm quota support activation on device: %s', partitionDevice);
			} else {
				dialogMessage = _('Please confirm quota support deactivation on device: %s', partitionDevice);
			}
			dialog.confirm(dialogMessage, [{
				label: _('OK'),
				callback: lang.hitch(this, function() {
					tools.umcpCommand('quota/partitions/' + (doActivate ? 'activate' : 'deactivate'),
									  	  {"partitionDevice" : partitionDevice.shift()}).then(
										  	  lang.hitch(this, function(data) {
											  	  if (data.result.success === true) {
												  	  this._grid.filter({'dummy': 'dummy'});
											  	  } else {
												  	  this._showActivateQuotaDialog(data.result, doActivate);
											  	  }
										  	  })
									  	  );
				})
			}, {
				label: _('Cancel')
			}]);
		},

		_showActivateQuotaDialog: function(result, doActivate) {
			var message = [];
			if (doActivate === true) {
				message = _('Failed to activate quota support: ');
			} else {
				message = _('Failed to deactivate quota support: ');
			}
			array.forEach(result.objects, function(item) {
				if (item.success === false) {
					message = message + item.message;
				}
			});
			dialog.confirm(message, [{
				label: _('OK')
			}]);
		},

		createPageContainer: function(partitionDevice) {
			this._pageContainer = new PageContainer({
				title: partitionDevice,
				closable: true,
				moduleID: this.moduleID,
				partitionDevice: partitionDevice
			});
			this.addChild(this._pageContainer);
			this.selectChild(this._pageContainer);
		}
	});
});
