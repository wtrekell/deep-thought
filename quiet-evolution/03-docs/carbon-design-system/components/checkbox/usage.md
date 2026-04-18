---
tool: web
url: "https://carbondesignsystem.com/components/checkbox/usage/"
mode: documentation
title: "Checkbox – Carbon Design Systeminfo iconOpen menuOpen menu"
word_count: 1608
processed_date: 2026-04-14T05:07:32.999136+00:00
---

# Checkbox

  * [Usage](https://carbondesignsystem.com/components/checkbox/usage/)
  * [Style](https://carbondesignsystem.com/components/checkbox/style/)
  * [Code](https://carbondesignsystem.com/components/checkbox/code/)
  * [Accessibility](https://carbondesignsystem.com/components/checkbox/accessibility/)

Checkboxes are used when there are multiple items to select in a list. Users can select zero, one, or any number of items.

info icon

Checkbox [with AI label](https://react.carbondesignsystem.com/?path=/story/components-checkbox--with-ai-label) is now stable. This addition changes the visual appearance of the component and introduces an AI explainability feature when AI is present in the component. See the [AI presence](https://carbondesignsystem.com/components/checkbox/usage/#ai-presence) section for more details.

  * Live demo
  * Overview
  * Formatting
  * Content
  * Behaviors
  * AI presence
  * Related
  * References
  * Feedback

## Live demo

Theme selector

White

Open menu

* * *

Variant selector

Default

Open menu

* * *

This live demo contains only a preview of functionality and styles available for this component. View the [full demo](https://react.carbondesignsystem.com/?path=/story/components-checkbox--default&globals=theme:white) on Storybook for additional information such as its version, controls, and API documentation.

### Accessibility testing status

For every latest release, Carbon runs tests on all components to meet the [accessibility requirements](https://www.ibm.com/able/requirements/requirements/). These different statuses report the work that Carbon has done in the back end. These tests appear only when the components are stable.

##### [Default stateTested](https://carbondesignsystem.com/components/checkbox/accessibility/#accessibility-testing-status)

##### [Advanced statesTested](https://carbondesignsystem.com/components/checkbox/accessibility/#accessibility-testing-status)

##### [Screen readerManually tested](https://carbondesignsystem.com/components/checkbox/accessibility/#accessibility-testing-status)

##### [Keyboard navigationTested](https://carbondesignsystem.com/components/checkbox/accessibility/#accessibility-testing-status)

## Overview

Checkboxes are used for multiple choices, not for mutually exclusive choices. Each checkbox works independently from other checkboxes in the list, therefore checking an additional box does not affect any other selections.

### When to use

#### Forms

Can be used in forms on a full page, in modals, or on side panels.

#### Filtering and batch action

Used to filter data either on a page, in a menu, or within a component. Checkboxes are found in [Data table](https://www.carbondesignsystem.com/components/data-table/usage) for batch editing purposes.

#### Terms and conditions

Turning the checkbox input on or off can indicate whether you agree to the terms.

#### Lists with sub-selections

Used when there is a parent and child relationship. You can use a parent checkbox to make a bulk selection of all list items. Unchecking the parent deselects all of the list items. Alternatively, you can select children individually when the parent is not selected, which is where the indeterminate state comes in to play.

Example of a full page filter list

### When not to use

If a user can select only one option from a list, radio buttons should be used instead of checkboxes. Checkboxes allow the user to select multiple items in a set whereas radio buttons allow the user to select only one option.

Do use radio buttons when only one item can be selected.

Don't use checkboxes when only one item can be selected.

## Formatting

### Anatomy

The checkbox component is comprised of a checkbox label and a checkbox input. If there is a group of checkboxes, a group label can be added.

  1. **Group label (optional):** Communicates what needs to be selected below.
  2. **Checkbox input:** A checkbox input indicating the appropriate state. By default it is unselected.
  3. **Checkbox label:** Describes the information you want to select or unselect.

### Alignment

Checkbox labels are positioned to the right of their inputs. If there is a checkbox grouping, they can be laid out vertically or horizontally depending on the use case and the structure of the UI. When possible, arrange the checkbox and radio button groups vertically for easier reading.

Vertically stacked versus horizontal alignment

### Placement

The checkbox component is often used in forms. Forms can be placed on a full page, in a modal or in a side panel. A checkbox can also be used for agreeing to terms and conditions or to filter information.

Checkboxes in a form should be placed at least 32px (`layout-03`) below or before the next component. Spacing of 24px (`layout-02`) or 16px (`layout-01`) can also be used when space is more restricted or if the form is more complex.

For more information on spacing in forms, see our [form style guidance](https://www.carbondesignsystem.com/components/form/style).

Spacing between a checkbox and other components in a form

For more information about spacing for the checkbox component itself, see the [style tab](https://www.carbondesignsystem.com/components/checkbox/style#structure).

## Content

### Main elements

#### Group labels (optional)

  * In most cases, a set of checkboxes is preceded by a group label to provide further context or clarity.
  * A group label can either state the category of the grouping or describe what actions to take below.
  * Use sentence case for group labels.
  * In some cases, a group of checkboxes may be within a larger group of components that already have a group label. In this case, an additional group label for the checkbox component itself is not needed.

#### Checkbox labels

  * Always use clear and concise labels for checkboxes.
  * Labels appear to the right of checkbox inputs.
  * Regardless of whether the label is visible in the interface, a label is always needed in code, whether it’s for one checkbox or a group of them. See the [checkbox code tab](https://www.carbondesignsystem.com/components/checkbox/code) for more information.

### Overflow content

  * We recommend checkbox labels being fewer than three words.
  * If you are tight on space, consider rewording the label. Do not truncate checkbox label text with an ellipsis.
  * Long labels may wrap to a second line, and this is preferable to truncation.
  * Text should wrap beneath the checkbox so the control and label are top aligned.

Do let text wrap beneath the checkbox so the control and label are top aligned.

Do not vertically center wrapped text with the checkbox.

### Further guidance

For further content guidance, see Carbon’s [content guidelines](https://carbondesignsystem.com/guidelines/content/overview).

## Behaviors

### States

The checkbox input allows for a series of states: **unselected** , **selected** , and **indeterminate**. The default view of a set of checkboxes is having no option selected.

Use the indeterminate state when the checkbox contains a sublist of selections, some of which are selected, and some unselected. In addition to unselected, selected, and indeterminate states, checkboxes also have states for focus, disabled, read-only, error, and warning. When deciding whether to use a disabled or read-only state for checkboxes, see our [Read-only states pattern](https://carbondesignsystem.com/patterns/read-only-states-pattern/) guidance.

#### Group states

Checkbox groups can receive the following states: read-only, disabled, error, and warning, as well as the addition of helper text.

### Nesting

Checkboxes can be nested when a parent and child relationship is needed. Users can either select an entire set of options or only a subset.

Checking the parent checkbox automatically selects all of the nested children checkboxes. Unchecking the parent checkbox automatically deselects all of the children checkboxes.

Checking a child checkbox, if at least one other child checkbox is not selected, automatically puts the parent checkbox into the indeterminate state. Unchecking a child checkbox, when all other children checkboxes remain selected, switches the parent checkbox from the default checked state to the indeterminate state.

### Interactions

#### Mouse

Users can trigger an item by clicking the checkbox input directly or by clicking the checkbox label. Having both regions interactive creates a more accessible click target. The only hover effect when the mouse is placed over the target is a pointer shape change.

#### Keyboard

Users can navigate to and between checkbox inputs by pressing `Tab` or `Shift-Tab`. Users can trigger a state change by pressing `Space` while the checkbox input has focus. For additional keyboard interactions, see the [accessibility tab](https://www.carbondesignsystem.com/components/checkbox/accessibility).

## AI presence

Checkbox has a modification that embeds the AI label when AI is present in the control. The AI variant functions the same as the normal version except with the addition of the AI label which is both a visual indicator and the trigger for the explainability popover. The AI label can be placed on the checkbox group label or on individual checkbox labels.

For more information on designing for AI, see the [Carbon for AI](https://carbondesignsystem.com/guidelines/carbon-for-ai/) guidelines.

## Related

#### Checkbox versus radio button

Radio buttons represent a group of _mutually exclusive_ choices, while checkboxes allow users to select one or more checkboxes from a group. In use cases where only one selection of a group is allowed, use the radio button component instead of the checkbox.

#### Checkbox versus toggle switch

Toggle switches are preferred when the resulting action will be instantaneously applied, without the need for further confirmation. By comparison, checkboxes represent one input in a larger flow which usually requires a final confirmation step.

#### Tables

See the [data table component](https://www.carbondesignsystem.com/components/data-table/usage#multiselect-batch-action) for guidance on how to use checkboxes within a table.

## References

  * [Data table](https://www.carbondesignsystem.com/components/data-table/usage)
  * [Form](https://www.carbondesignsystem.com/components/form/usage)
  * [Radio button](https://www.carbondesignsystem.com/components/radio-button/usage)
  * [Toggle](https://www.carbondesignsystem.com/components/toggle/usage)

## Feedback

Help us improve this component by providing feedback, asking questions, and leaving any other comments on [GitHub](https://github.com/carbon-design-system/carbon-website/issues/new?assignees=&labels=feedback&template=feedback.md).

[Edit this page on GitHub](https://github.com/carbon-design-system/carbon-website/edit/main/src/pages/components/checkbox/usage.mdx)

  * [Contact us](https://www.carbondesignsystem.com/help/contact-us)
  * [Privacy](https://www.ibm.com/privacy)
  * [Terms of use](https://www.ibm.com/legal)
  * [Accessibility](https://www.ibm.com/able)
  * [IBM.com](https://www.ibm.com/)

  * [Medium](https://medium.com/carbondesign)
  * [𝕏](https://x.com/_carbondesign)

Have questions? Email us   
at [carbon@us.ibm.com](mailto:carbon@us.ibm.com)   
or open an issue on [GitHub.](https://github.com/carbon-design-system/carbon-website/issues/new)

React Components version ^1.105.0  
Last updated 09 April 2026  
Copyright © 2026 IBM

IBM web domains

ibm.com, ibm.org, ibm-zcouncil.com, insights-on-business.com, jazz.net, mobilebusinessinsights.com, promontory.com, proveit.com, ptech.org, s81c.com, securityintelligence.com, skillsbuild.org, softlayer.com, storagecommunity.org, think-exchange.com, thoughtsoncloud.com, alphaevents.webcasts.com, ibm-cloud.github.io, ibmbigdatahub.com, bluemix.net, mybluemix.net, ibm.net, ibmcloud.com, galasa.dev, blueworkslive.com, swiss-quantum.ch, blueworkslive.com, cloudant.com, ibm.ie, ibm.fr, ibm.com.br, ibm.co, ibm.ca, community.watsonanalytics.com, datapower.com, skills.yourlearning.ibm.com, bluewolf.com, carbondesignsystem.com, openliberty.io 

About cookies on this site Our websites require some cookies to function properly (required). In addition, other cookies may be used with your consent to analyze site usage, improve the user experience and for advertising. For more information, please review your cookie preferences options. By visiting our website, you agree to our processing of information as described in IBM’s[privacy statement](https://www.ibm.com/privacy).  To provide a smooth navigation, your cookie preferences will be shared across the IBM web domains listed here.

Accept all More options

Cookie Preferences