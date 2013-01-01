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
	"umc/tools",
	"umc/widgets/Page",
	"umc/widgets/Form",
	"umc/widgets/TextBox",
	"umc/widgets/ComboBox",
	"umc/i18n!umc/modules/setup"
], function(declare, lang, array, tools, Page, Form, TextBox, ComboBox, _) {
	return declare("umc.modules.setup.CertificatePage", [ Page ], {
		// summary:
		//		This class renderes a detail page containing subtabs and form elements
		//		in order to edit UDM objects.

		// system-setup-boot
		wizard_mode: false,

		// __systemsetup__ user is logged in at local firefox session
		local_mode: false,

		umcpCommand: tools.umcpCommand,

		// internal reference to the formular containing all form widgets of an UDM object
		_form: null,

		_noteShowed: false,

		_doShowNote: false,

		_orgVals: null,
		old_ssl_email: null,

		postMixInProperties: function() {
			this.inherited(arguments);

			this.title = _('Certificate');
			this.headerText = _('Certificate settings');
			this.helpText = _('Following the <i>certificate settings</i>, a new root certificate will be created for the domain. Note that this step only applies to systems with the role "domaincontroller master".');
			this._orgVals = {};
		},

		buildRendering: function() {
			this.inherited(arguments);

			var widgets = [{
				type: TextBox,
				name: 'ssl/common',
				label: _('Common name for the root SSL certificate'),
				umcpCommand: this.umcpCommand,
				dynamicValues: 'ssl/lang/countrycodes'
			}, {
				type: ComboBox,
				name: 'ssl/country',
				label: _('Country'),
				umcpCommand: this.umcpCommand,
				dynamicValues: 'setup/lang/countrycodes'
			}, {
				type: TextBox,
				name: 'ssl/state',
				label: _('State')
			}, {
				type: TextBox,
				name: 'ssl/locality',
				label: _('Location')
			}, {
				type: TextBox,
				name: 'ssl/organization',
				label: _('Organization')
			}, {
				type: TextBox,
				name: 'ssl/organizationalunit',
				label: _('Business unit')
			}, {
				type: TextBox,
				name: 'ssl/email',
				label: _('Email address')
			}];

			var layout = [{
				label: _('General settings'),
				layout: [ 'ssl/common', 'ssl/email' ]
			}, {
				label: _('Location settings'),
				layout: [ 'ssl/country', 'ssl/state', 'ssl/locality' ]
			}, {
				label: _('Organization settings'),
				layout: [ 'ssl/organization', 'ssl/organizationalunit' ]
			}];

			this._form = new Form({
				widgets: widgets,
				layout: layout,
				scrollable: true
			});
			this._form.on('submit', lang.hitch(this, 'onSave'));

			tools.forIn(this._form._widgets, function(iname, iwidget) {
				iwidget.on('KeyUp', lang.hitch(this, function() {
					if (iwidget.focused) {
						this._showNote();
					}
				}));
				this.own(iwidget.watch('value', lang.hitch(this, function() {
					if (iwidget.focused) {
						this._showNote();
					}
				})));
			}, this);

			this.addChild(this._form);
		},

		_showNote: function() {
			if (!this._noteShowed && this._doShowNote) {
				this._noteShowed = true;
				this.addNote(_('Changes in the SSL certificate settings will result in generating new root SSL certificates. Note that this will require an update of all host certificates in the domain as the old root certificate is no longer valid. Additional information can be found in the <a href="http://sdb.univention.de/1000" target="_blank">Univention Support Database</a>'));
			}
		},

		setValues: function(_vals) {
			// update ssl/email on FQDN changes if not manually changed
			if(!this.old_ssl_email) {
				this.old_ssl_email = this._orgVals['ssl/email'];
			}
			if( _vals['ssl/email'] === this.old_ssl_email) {
				_vals['ssl/email'] = this.old_ssl_email = 'ssl@' + _vals.domainname;
			}

			this._form.setFormValues(_vals);
			this._orgVals = lang.clone(_vals);
			this.clearNotes();

			this._doShowNote = !this.wizard_mode;

			// this page should be only visible on domaincontroller_master
			this.set('visible', _vals['server/role'] == 'domaincontroller_master');

			// reset the flag indicating whether certificate note has been shown or not
			// we do not need to show the note in appliance mode
			this._noteShowed = tools.status('username') == '__systemsetup__';
		},

		getValues: function() {
			return this._form.gatherFormValues();
		},

		getSummary: function() {
			// a list of all countries
			var allCountries = {};
			array.forEach(this._form.getWidget('ssl/country').getAllItems(), function(iitem) {
				allCountries[iitem.id] = iitem.label;
			});

			var vals = this.getValues();
			vals['ssl/country'] = allCountries[vals['ssl/country']];
			return [{
				variables: [/^ssl\/.*/],
				description: _('SSL root certificate'),
				values: lang.replace('{ssl/common}, {ssl/email}, {ssl/organization}, {ssl/organizationalunit}, {ssl/locality}, {ssl/state}, {ssl/country}', vals)
			}];
		},

		onSave: function() {
			// event stub
		},

		onValuesChanged: function() {
			// event stub
		}
	});
});
