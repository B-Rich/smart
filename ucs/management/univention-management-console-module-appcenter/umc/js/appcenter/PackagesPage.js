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
	"umc/dialog",
	"umc/tools",
	"umc/widgets/Page",
	"umc/widgets/Grid",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/ProgressBar",
	"umc/modules/lib/server",
	"umc/modules/appcenter/SearchForm",
	"umc/i18n!umc/modules/appcenter"
], function(declare, lang, array, dialog, tools, Page, Grid, ConfirmDialog, ProgressBar, libServer, SearchForm, _) {
	return declare("umc.modules.appcenter.PackagesPage", [ Page ], {

		moduleStore: null,
		standby: null, // parents standby method must be passed. weird IE-Bug (#29587)

		postMixInProperties: function() {
			this.inherited(arguments);

			lang.mixin(this, {
				headerText: _("Extended software management"),
				helpText: _("On this page, you see all software packages available on your system, and you can install, uninstall or update them."),
				title: _("Extended software management")
			});
		},

		buildRendering: function() {

			this.inherited(arguments);

			this._progressBar = new ProgressBar();
			this.own(this._progressBar);

			this._form = new SearchForm({
				region: 'top'
			});
			this._form.on('submit', lang.hitch(this, function() {
				this._refresh_grid();
			}));

			var actions = [
				{
					name: 'view',
					label: _("View Details"),
					isContextAction: true,
					isStandardAction: false,
					isMultiAction: false,
					callback: lang.hitch(this, function(ids) {
						this._show_details(ids);
					})
				},
				// isStandardAction=true for the installer actions (install/uninstall/upgrade)
				// doesn't make sense as long as these actions aren't displayed as icons
				{
					name: 'install',
					label: _("Install"),
					isContextAction: true,
					isStandardAction: false,
					isMultiAction: true,
					canExecute: lang.hitch(this, function(values) {
						return this._can_install(values);
					}),
					callback: lang.hitch(this, function(ids) {
						this._call_installer('install', ids);
					})
				},
				{
					name: 'uninstall',
					label: _("Uninstall"),
					isContextAction: true,
					isStandardAction: false,
					isMultiAction: true,
					canExecute: lang.hitch(this, function(values) {
						return this._can_uninstall(values);
					}),
					callback: lang.hitch(this, function(ids) {
						this._call_installer('uninstall', ids);
					})
				},
				{
					name: 'upgrade',
					label: _("Upgrade"),
					isContextAction: true,
					isStandardAction: false,
					isMultiAction: true,
					canExecute: lang.hitch(this, function(values) {
						return this._can_upgrade(values);
					}),
					callback: lang.hitch(this, function(ids) {
						this._call_installer('upgrade', ids);
					})
				}
			];

			var columns = [
				{
					name: 'package',
					label: _("Package name")
				},
				//{
				//	name: 'section',
				//	width: 'adjust',
				//	label: _("Section")
				//},
				{
					name: 'summary',
					label: _("Package description")
				},
				{
					name: 'status',
					label: _("Installation status"), // notinstalled/installed/upgradable
					width: 'adjust'
				}
			];

			// create a grid in the 'center' region
			this._grid = new Grid({
				region: 'center',
				actions: actions,
				columns: columns,
				moduleStore: this.moduleStore,
				defaultAction: 'view',
				onFilterDone: lang.hitch(this, function() {
					this._form.allowSearchButton(true);
				})
			});

			this._refresh_grid();
			this.addChild(this._form);
			this.addChild(this._grid);
		},

		_refresh_grid: function() {

			var values = this._form.gatherFormValues();
			if (values.section) {
				this._form.allowSearchButton(false);
				this._grid.filter(values);
			}
		},

		// shows details about a package in a popup dialog
		_show_details: function(ids) {

			var id = ids;
			if (ids instanceof Array) {
				id = ids[0];
			}

			this._grid.standby(true);

			this.moduleStore.umcpCommand('appcenter/packages/get', {'package': id}).then(
				lang.hitch(this, function(data) {

					this._grid.standby(false);

					var head_style	= 'font-size:120%;font-weight:bold;margin:.5em;text-decoration:underline;';
					var label_style = 'vertical-align:top;text-align:right;padding-left:1em;padding-right:.5em;white-space:nowrap;font-weight:bold;';
					var data_style	= 'vertical-align:top;padding-bottom:.25em;';

					var txt = "<p style='" + head_style + "'>" +
						lang.replace(_("Details for package '{package}'"), data.result) +
						"</p>";
					txt += '<table>\n';
					var width = 550;	// mimic the default of dialog.confirm
					array.forEach(this._detail_field_order(), lang.hitch(this, function(f) {
						if (typeof(data.result[f]) != 'undefined') {
							var fl = this._detail_field_label(f);
							if (fl) {
								txt += "<tr>\n";
								txt += "<td style='" + label_style + "'>" + fl + "</td>\n";
								// ----------------------------------------------------------------
								// if you think the following logic is not needed...
								// just open the 'devscripts' package and see for yourself.
								var dfv = this._detail_field_value(f, data.result[f]);
								var maxlen = 3000;
								if (dfv.length > maxlen) {
									// cut text at 'maxlen' chars, optionally adding a hint.
									dfv = dfv.substr(0, maxlen) + _("...<br>[%d more chars]", dfv.length-maxlen);
								}
								if (f == 'description') {
									// adjust width according to the length of the 'description' field.
									width = 500 + (dfv.length / 10);
								}
								// ----------------------------------------------------------------
								txt += "<td style='" + data_style + "'>" + dfv + "</td>\n";
								txt += "</tr>\n";
							}
						}
					}));
					txt += "</table>\n";
					var buttons = [];
					if (this._can_install(data.result)) {
						buttons.push({
							name: 'install',
							label: _("Install"),
							callback: lang.hitch(this, function() {
								this._call_installer('install', [data.result['package']]);
							})
						});
					}
					if (this._can_uninstall(data.result)) {
						buttons.push({
							name: 'uninstall',
							label: _("Uninstall"),
							callback: lang.hitch(this, function() {
								this._call_installer('uninstall', [data.result['package']]);
							})
						});
					}
					if (this._can_upgrade(data.result)) {
						buttons.push({
							name: 'upgrade',
							label: _("Upgrade"),
							callback: lang.hitch(this, function() {
								this._call_installer('upgrade', [data.result['package']]);
							})
						});
					}
					// always: a button to close the dialog.
					buttons.push({
						name: 'cancel',
						'default': true,
						label: _("Close")
					});

					var confirmDialog = new ConfirmDialog({
						title: _('Package details'),
						style: lang.replace('min-width:500px;max-width: {width}px;', {width: width}), // dialog.confirm doesn't exceed 550px
						message: txt,
						options: buttons
					});

					// connect to 'onConfirm' event to close the dialog in any case
					confirmDialog.on('confirm', function() {
						confirmDialog.close();
					});

					// show the confirmation dialog
					confirmDialog.show();

				}),
				lang.hitch(this, function(data) {
					this._grid.standby(false);
				})
			);
		},

		// Helper function that returns the field names for the
		// detail view in a well-defined order
		_detail_field_order: function() {

			return (['package',
				 'summary',
				 'section',
				 'installed',
				 'installed_version',
				 'upgradable',
				 'candidate_version',
				 'size',
				 'priority',
				 'description'
				 ]);
		},

		// Helper function that translates field names for the detail view. This
		// is made for two purposes:-
		//
		//	(1)	this way, we can mention the entries in the source, so our
		//		automated .po file maintainer script can see them
		//	(2)	fields not mentioned here should not be displayed in the detail view
		_detail_field_label: function(name) {
			var labels = {
				'package': _("Package name"),
				'section': _("Section"),
				'summary': _("Summary"),
				'description': _("Description"),
				'installed': _("Is installed"),
				'upgradable': _("Is upgradable"),
				'size': _("Package size"),
				'priority': _("Priority"),
				'installed_version': _("Installed version"),
				'candidate_version': _("Candidate version")
			};
			return labels[name];
		},

		// Helper function that translates field values. Mainly used for:
		//
		//	(1)	boolean to text (according to field name)
		//	(2)	HTML-escaping free text (summary, description)
		//	(3)	adding (eventually) icons
		//
		_detail_field_value: function(name, value) {

			switch(name) {
				case 'summary':
				case 'description':
					// TODO find or write a decoder function
					return value;		// for now
				case 'installed':
				case 'upgradable':
					if ((value === 'true') || (value === true)) {
						return _("Yes");
					}
					return _("No");
			}
			// fallback: return value unchanged
			return value;
		},

		// Helper functions that determine if a given function can be executed.
		// will be called from different places:-
		//
		//	(1)	in the 'canExecute' callbacks of grid rows
		//	(2)	in the detail view to determine which buttons to show
		//
		_can_install: function(values) {
			return !values.installed && !this._breaks_anything(values);
		},
		_can_uninstall: function(values) {
			return values.installed && !this._breaks_anything(values);
		},
		_can_upgrade: function(values) {
			return values.upgradable && !this._breaks_anything(values);
		},
		_breaks_anything: function(values) { return values.breaks !== undefined && values.breaks.length; },

		// prepares all data for the acutal execution of the installer.
		_call_installer: function(func, ids) {
			var verb = '';
			var verb1 = '';
			switch(func) {
				case 'install':
					verb = _("install");
					verb1 = _("installing");
					break;
				case 'uninstall':
					verb = _("uninstall");
					verb1 = _("uninstalling");
					break;
				case 'upgrade':
					verb = _("upgrade");
					verb1 = _("upgrading");
					break;
			}

			this.standby(true);
			tools.umcpCommand('appcenter/packages/invoke/test', {'function': func, 'packages': ids}).then(lang.hitch(this, function(data) {
				this.standby(false);
				var result = data.result;
				var txt = '';
				var label = '';
				if (result.install.length) {
					label = _('The following packages will be installed or upgraded:');
					txt += '<p>' + label + '<ul><li>' + result.install.join('</li><li>') + '</li></ul></p>';
				}
				if (result.remove.length) {
					label = _('The following packages will be removed:');
					txt += '<p>' + label + '<ul><li>' + result.remove.join('</li><li>') + '</li></ul></p>';
				}
				if (result.broken.length) {
					label = _('This operation causes problems in the following packages that cannot be resolved:');
					txt += '<p>' + label + '<ul><li>' + result.broken.join('</li><li>') + '</li></ul></p>';
				}
				var headline = '';
				var buttons = [];
				if (result.broken.length) {
					headline = _('You cannot continue');
					buttons = [
						{
							name: 'cancel',
							'default': true,
							label: _("Cancel")
						}
					];
				} else {
					headline = lang.replace(_("Do you really want to {verb} {ids}?"), {verb: verb, ids: ids.join(', ')});
					var msg = lang.replace(_("You're currently {verb} {ids}"), {verb: verb1, ids: ids.join(', ')});
					buttons = [
						{
							name: 'cancel',
							label: _("No")
						},
						{
							name: 'submit', // I want to catch <Enter> too
							'default': true,
							label: _("Yes"),
							callback: lang.hitch(this, function() {
								this._execute_installer(func, ids, msg);
							})
						}
					];
				}

				dialog.confirm('<p><strong>' + headline + '</strong></p>' + txt, buttons);
			}));
		},

		// Starts the installer and switches to progress view.
		_execute_installer: function(func, ids, msg) {

			this.moduleStore.umcpCommand('appcenter/packages/invoke', {'function': func, 'packages': ids}).then(lang.hitch(this, function(data) {
				if (data.result.not_found.length) {
					dialog.alert(_('Packages not found: ') + data.result.not_found.join(', '));
				} else {
					this._switch_to_progress_bar(msg);
				}
			}));
		},

		_switch_to_progress_bar: function(msg) {
			this.standby(true, this._progressBar);
			this._progressBar.reset(msg);
			this._progressBar.auto('appcenter/packages/progress',
				{},
				lang.hitch(this, '_restartOrReload')
			);
		},

		_restartOrReload: function() {
			// TODO: only if necessary! only minority will require a restart!
			libServer.askRestart(_('A restart of the UMC server components may be necessary for the software changes to take effect.')).then(
			function() {
				// if user confirms, he is redirected to the login page
				// no need to do anythin fancy here :)
			},
			lang.hitch(this, function() {
				// user canceled -> switch back to initial view
				this.standby(false);
				this._refresh_grid();
			}));
		}

	});
});

