---
tool: web
url: "https://carbondesignsystem.com/components/code-snippet/usage/"
mode: documentation
title: "Code snippet – Carbon Design SystemOpen menuOpen menu"
word_count: 1191
processed_date: 2026-04-14T05:07:35.291700+00:00
---

# Code snippet

  * [Usage](https://carbondesignsystem.com/components/code-snippet/usage/)
  * [Style](https://carbondesignsystem.com/components/code-snippet/style/)
  * [Code](https://carbondesignsystem.com/components/code-snippet/code/)
  * [Accessibility](https://carbondesignsystem.com/components/code-snippet/accessibility/)

Code snippets are strings or small blocks of reusable code that can be copied and inserted in a code file.

  * Live demo
  * Overview
  * Formatting
  * Content
  * Universal behaviors
  * Inline
  * Single line
  * Multi-line
  * Modifiers
  * Feedback

## Live demo

Theme selector

White

Open menu

* * *

Variant selector

Inline

Open menu

* * *

This live demo contains only a preview of functionality and styles available for this component. View the [full demo](https://react.carbondesignsystem.com/?path=/story/components-codesnippet--inline&globals=theme:white) on Storybook for additional information such as its version, controls, and API documentation.

### Accessibility testing status

For every latest release, Carbon runs tests on all components to meet the [accessibility requirements](https://www.ibm.com/able/requirements/requirements/). These different statuses report the work that Carbon has done in the back end. These tests appear only when the components are stable.

##### [Default statePartially tested](https://carbondesignsystem.com/components/code-snippet/accessibility/#accessibility-testing-status)

##### [Advanced statesTested](https://carbondesignsystem.com/components/code-snippet/accessibility/#accessibility-testing-status)

##### [Screen readerManually tested](https://carbondesignsystem.com/components/code-snippet/accessibility/#accessibility-testing-status)

##### [Keyboard navigationTested](https://carbondesignsystem.com/components/code-snippet/accessibility/#accessibility-testing-status)

## Overview

There are three different variants of code snippets to help cater to varied line length use cases—inline, single line, and multi-line.

### Variants

Variant| Purpose  
---|---  
Inline| A block of text used inline with sentences or paragraphs.  
Single line| A single line of code.  
Multi-line| Multiple lines of code with the ability to show more or less strings.  
  
### When to use

  * Use a code snippet to help the user copy strings of text easily, or if you want to call out key words for the user.
  * Code snippets are typically used in code documentation to help the user get started quickly.

### When not to use

  * Do not use a code snippet if you want the user to change the input value. Our code snippets are read only.

## Formatting

### Anatomy

  1. **Snippet text:** Lines or a block of code.
  2. **Copy button (optional)** : An icon button to copy the code to the clipboard.
  3. **Show more button (optional)** : A ghost button to expand or collapse the code snippet to show more or fewer lines of code.

### Placement

Code snippet containers should vertically align to the grid with other form components on a page.

_Note: If using an inline code snippet, the snippet will live within a body of text._

Do align code snippet containers to the grid.

Do not align code snippet text to the grid and hang the container.

## Content

### Main elements

#### Snippet text

  * Make sure the code is using the correct syntax so that the code will not break if the user copies it to their clipboard.

#### Copy button tooltip

  * The copy button should be accompanied by a tooltip. Tooltip feedback text should be concise and describe the action taken when the user clicks the copy button. By default we display the text “Copied to clipboard”.

#### Show more button

  * The ghost button text should describe what the button will reveal or hide when the user clicks it. By default we display the text “Show more” or “Show less”.

### Further guidance

For further content guidance, see Carbon’s [content guidelines](https://carbondesignsystem.com/guidelines/content/overview).

## Universal behaviors

### Copy to clipboard

Code snippets by default have a copy functionality that allows users to copy the provided code to their clipboard. The copy icon must be accompanied by a confirmation tooltip that states the successful action of copying an item to the clipboard. Having copy functionality is optional and can be removed if it’s not necessary for your use case.

## Interactions

#### Mouse

An inline code snippet can be copied by clicking anywhere on the snippet itself.

A single line code snippet can be copied by clicking on the “copy” icon. The browser also provides an ability to manually highlight the text and choose “copy” from the context menu (right click).

A multi-line code snippet can be copied by clicking on the copy icon or by manually highlighting the text and right clicking “copy”.

#### Keyboard

#### Copy button:

  * An inline code snippet, and the copy button of the single line and multiline snippets can be focused by pressing `Tab`.
  * The copy functionality can be activated by pressing either `Space` or `Enter`.
  * After the copy is activated, the focus remains on the button since there is no change in context.

#### Show more button:

  * The “Show more” ghost button in the multi-line code snippet can be focused by pressing `Tab`.
  * Show more or less code by pressing `Space` or `Enter` while the ghost button is in focus.

For additional keyboard interactions, see the [accessibility tab](https://carbondesignsystem.com/components/code-snippet/accessibility#keyboard-interaction).

## Inline

Use inline code snippets within bodies of text. Using code snippets inline helps create emphasis on important key words to copy and makes long bodies of text easier to scan. Refrain from having inline code snippets that extend to multiple lines.

## Single line

Use single line code snippets for longer strings of code that can still be presented on one line.

### Single line overflow content

If the text in a single line code snippet is lengthy, the text overflows into a horizontal scroll.

## Multi-line

Use multi-line code snippets for displaying multiple lines of code.

### Multi-line overflow content

#### Show more button

A Show more ghost button can be added to a multi-line code snippet to show more or fewer lines of code. Use this functionality if your layout is tight on space.

#### Vertical scroll

Alternatively, you can apply vertical scrolling to the code snippet if there are more than nine lines of code.

#### Horizontal scroll

Terminal commands are often longer strings and should only appear on one line. Apply horizontal scrolling to maintain the set width of the box for these longer strings.

## Modifiers

#### Light

Use the `light` prop modifier when using a code snippet on a background other than the UI background for that theme. The light prop changes the background color token of the code snippet from `field-01` to `field-02`.

## Feedback

Help us improve this component by providing feedback, asking questions, and leaving any other comments on [GitHub](https://github.com/carbon-design-system/carbon-website/issues/new?assignees=&labels=feedback&template=feedback.md).

[Edit this page on GitHub](https://github.com/carbon-design-system/carbon-website/edit/main/src/pages/components/code-snippet/usage.mdx)

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