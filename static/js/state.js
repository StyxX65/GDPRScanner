// state.js — shared mutable state for GDPRScanner
// Imported by every module that needs cross-module state.
// Use S.varName everywhere instead of bare varName.

export const S = {
  // Scan results
  flaggedData:          [],
  filteredData:         [],
  totalCPR:             0,
  isListView:           false,
  // SSE connection
  es:                   null,
  _userStartedScan:     false,
  // Scan running flags + progress
  _m365ScanRunning:     false,
  _googleScanRunning:   false,
  _fileScanRunning:     false,
  _srcPct:              { m365: 0, google: 0, file: 0 },
  _progressCurrentUser: '',
  // Users
  _allUsers:            [],
  // Auth
  _currentAppMode:      null,
  // Profiles
  _profiles:            [],
  _activeProfileId:     null,
  _pendingProfileSources: [],
  _pendingGoogleSources:  null,
  // Sources
  _fileSources:         [],
  // History browser
  _historyRefScanId:    null,   // null = live/SSE, number = viewing a past session
  // Bulk disposition
  _selectMode:          false,
  _selectedIds:         new Set(),
};
