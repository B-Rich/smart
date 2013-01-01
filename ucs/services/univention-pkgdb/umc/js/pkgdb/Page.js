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
/*global define console*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/aspect",
	"dojo/dom-class",
	"umc/tools",
	"umc/store",
	"umc/widgets/Grid",
	"umc/widgets/Page",
	"umc/widgets/StandbyMixin",
	"umc/widgets/ExpandingTitlePane",
	"umc/modules/pkgdb/SearchForm",
	"umc/modules/pkgdb/KeyTranslator",
	"umc/i18n!umc/modules/pkgdb"
], function(declare, lang, aspect, domClass, tools, store, Grid, Page, StandbyMixin, ExpandingTitlePane, SearchForm, KeyTranslator, _) {

	// Page with a unified layout
	//
	//	-	whole thing stuffed into an ExpandingTitlePane
	//	-	one-line search form (for now...?)
	//	-	results grid
	//
	// Which page ('flavor') to show is determined by the 'pageKey'
	// attribute being set by the constructor call.
	//
	return declare("umc.modules.pkgdb.Page", [ Page, StandbyMixin, KeyTranslator], {
		
		_grid:						null,			// holds the results grid if query was invoked at least once
		_last_table_structure:		null,			// remember last table structure
		_current_query:				null,			// what is being executed right now

		buildRendering: function() {

			this.inherited(arguments);

			this._pane = new ExpandingTitlePane({
				title:			this.title
			});
			this.addChild(this._pane);

			this._searchform = new SearchForm({
				region:			'top',
				pageKey:		this.pageKey
			});
			this._pane.addChild(this._searchform);

			// Listen to the submit event
			this._searchform.on('ExecuteQuery',lang.hitch(this, function(query) {
				this._execute_query(query);
			}));
		},

		// fetches the structure of the result grid. The callback returns
		// the current query to us.
		_execute_query: function(query) {

			this._current_query = query;

			try
			{
				tools.umcpCommand('pkgdb/columns',{
					page: this.pageKey,
					key: this._current_query.key
				}).then(lang.hitch(this, function(data) {
					this._create_table(data.result);
				}));
			}
			catch(error)
			{
				console.error('execute_query: ' + error.message);
			}
		},

		// Creates the given result table. 'fields' is an array of column names.
		// The corresponding query is already stored in this._current_query. 
		_create_table: function(fields) {

			try
			{
				// determine if we have already a grid structured like that
				var grid_usable = false;
				var sig = fields.join(':');
				if (this._grid)
				{
					if (this._last_table_structure && (this._last_table_structure == sig))
					{
						grid_usable = true;
					}
				}			
				this._last_table_structure = sig;

				if (! grid_usable)
				{			
					var columns = [];

					for (var f in fields)
					{
						var fname = fields[f];
						var entry = {
								name:	fname,
								label:	fname
							};
						var props = this._field_options(fname);
						if (props)
						{
							lang.mixin(entry,props);
						}
						columns.push(entry);
					}

					var newgrid = new Grid({
						region:			'center',
						actions:		[],
						columns:		columns,
						moduleStore:	store(fields[0],'pkgdb')
					});

					if (this._grid)
					{
						// detach and free old grid instance
						this._pane.removeChild(this._grid);
						this._grid.uninitialize();
						this._grid = null;
					}
					this._grid = newgrid;
					this._pane.addChild(this._grid);

					// No time to debug why this Grid does not call 'onFilterDone()'
					this._grid.on('FilterDone', lang.hitch(this, function(success) {
						this._searchform.enableSearchButton(true);
						this._searchform.enableEntryElements(true);
					}));
					aspect.after(this._grid._grid, '_onFetchComplete', lang.hitch(this, function() {
						this._searchform.enableSearchButton(true);
						this._searchform.enableEntryElements(true);
					}));
					aspect.after(this._grid._grid, '_onFetchError',lang.hitch(this, function() {
						this._searchform.enableSearchButton(true);
						this._searchform.enableEntryElements(true);
					}));
				}

				domClass.toggle(this._grid.domNode,'dijitHidden',false);

				// Execute the given query (a.k.a. filter) on the grid
				this._grid.filter(
					lang.mixin({
						page:	this.pageKey
					},
					this._current_query)
				);

			}
			catch(error)
			{
				console.error('create_table: ' + error.message);
			}
		}
	});
});
